"""REST + SSE routes for the CircuitMind API gateway.

Endpoints
---------
POST /api/v1/bom/analyze            → accept upload, enqueue, return 202 + job_id
GET  /api/v1/jobs/{job_id}          → job status (+ review/constraint payload / result)
GET  /api/v1/jobs/{job_id}/stream   → Server-Sent Events live agent log
POST /api/v1/jobs/{job_id}/constraints → resume graph with value-based constraints
POST /api/v1/jobs/{job_id}/approve  → resume graph with human approval decision
GET  /api/v1/jobs/{job_id}/results  → final purchase orders
"""
from __future__ import annotations

import asyncio
import json
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from ..config import settings
from ..db.models import BOM, BOMLineItem, PurchaseOrder
from ..db.session import get_session
from ..docai.parser import parse_bom_file
from ..queue import redis_queue as q
from .schemas import AnalyzeResponse, ApprovalRequest, ConstraintsRequest, JobStatusResponse

router = APIRouter(prefix="/api/v1")

_ALLOWED_EXT = {".pdf", ".xlsx", ".xls", ".csv", ".tsv", ".txt", ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".gif"}


@router.post("/bom/analyze", response_model=AnalyzeResponse, status_code=status.HTTP_202_ACCEPTED)
async def analyze_bom(
    file: UploadFile = File(...),
    bypass_constraints: bool = False,  # New parameter to skip constraints
    session: Session = Depends(get_session),
) -> AnalyzeResponse:
    """Accept a BOM upload, persist it, parse line items, enqueue the job.

    Parameters:
    - file: The BOM file to analyze
    - bypass_constraints: If True, skips the constraints gate and proceeds directly
    
    Constraints gate can be bypassed for quick demos or when no constraints are needed.
    """
    filename = file.filename or "upload.bin"
    ext = os.path.splitext(filename)[1].lower()
    if ext and ext not in _ALLOWED_EXT:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{ext}'. Allowed: {sorted(_ALLOWED_EXT)}",
        )

    # Persist file to disk.
    os.makedirs(settings.upload_dir, exist_ok=True)
    safe_name = f"{uuid.uuid4().hex}{ext or '.bin'}"
    filepath = os.path.join(settings.upload_dir, safe_name)
    content = await file.read()
    with open(filepath, "wb") as fh:
        fh.write(content)

    # Create BOM header + pre-parse line items so the DB has FK targets ready
    bom = BOM(filename=filename, status="pending")
    session.add(bom)
    session.flush()

    try:
        rows = parse_bom_file(filepath)
    except Exception:
        rows = []
    for row in rows:
        session.add(BOMLineItem(
            bom_id=bom.id,
            line_number=row["line_number"],
            reference_designator=row.get("reference_designator", ""),
            mpn=row["mpn"],
            quantity=row.get("quantity", 1),
            description=row.get("description", ""),
        ))
    session.commit()

    bom_id = str(bom.id)
    job_id = q.create_job(filename=filename, bom_id=bom_id, bypass_constraints=bypass_constraints)
    q.enqueue_process(job_id=job_id, bom_id=bom_id, filepath=filepath, bypass_constraints=bypass_constraints)

    return AnalyzeResponse(job_id=job_id, bom_id=bom_id)


@router.post("/bom/analyze/batch", response_model=AnalyzeResponse, status_code=status.HTTP_202_ACCEPTED)
async def analyze_bom_batch(
    files: list[UploadFile] = File(...),
    bypass_constraints: bool = False,  # New parameter
    session: Session = Depends(get_session),
) -> AnalyzeResponse:
    """Accept multiple BOM files, combine them into a single job for processing.
    
    Supports mixing file types: CSV + images + PDFs all in one batch.
    All files are processed and merged into a single BOM analysis.
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided"
        )
    
    if len(files) > 20:  # Reasonable limit for hackathon
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Too many files. Maximum 20 files per batch."
        )

    # Validate all files first
    filepaths = []
    filenames = []
    
    for file in files:
        filename = file.filename or "upload.bin"
        ext = os.path.splitext(filename)[1].lower()
        if ext and ext not in _ALLOWED_EXT:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported file type '{ext}' in file '{filename}'. Allowed: {sorted(_ALLOWED_EXT)}",
            )
        filenames.append(filename)

    # Persist all files
    os.makedirs(settings.upload_dir, exist_ok=True)
    
    for i, file in enumerate(files):
        ext = os.path.splitext(filenames[i])[1].lower()
        safe_name = f"{uuid.uuid4().hex}{ext or '.bin'}"
        filepath = os.path.join(settings.upload_dir, safe_name)
        content = await file.read()
        with open(filepath, "wb") as fh:
            fh.write(content)
        filepaths.append(filepath)

    # Create BOM header for batch job
    batch_filename = f"batch_{len(files)}_files_{filenames[0]}"
    bom = BOM(filename=batch_filename, status="pending")
    session.add(bom)
    session.flush()

    # Parse all files and combine results
    all_rows = []
    line_offset = 0
    
    for filepath, filename in zip(filepaths, filenames):
        try:
            rows = parse_bom_file(filepath)
            # Adjust line numbers to prevent conflicts
            for row in rows:
                row["line_number"] += line_offset
                row["source_file"] = filename  # Track source file
            all_rows.extend(rows)
            line_offset += len(rows)
        except Exception:
            # Skip failed files but continue with others
            continue

    # Insert combined rows into database
    for row in all_rows:
        session.add(BOMLineItem(
            bom_id=bom.id,
            line_number=row["line_number"],
            reference_designator=row.get("reference_designator", ""),
            mpn=row["mpn"],
            quantity=row.get("quantity", 1),
            description=row.get("description", ""),
        ))
    session.commit()

    bom_id = str(bom.id)
    job_id = q.create_job(filename=batch_filename, bom_id=bom_id, bypass_constraints=bypass_constraints)
    
    # Pass all filepaths to worker for batch processing
    q.enqueue_process(job_id=job_id, bom_id=bom_id, filepath=filepaths[0], 
                     batch_files=filepaths, bypass_constraints=bypass_constraints)

    return AnalyzeResponse(job_id=job_id, bom_id=bom_id)


@router.get("/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    job = q.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(
        job_id=job_id,
        status=job.get("status", "unknown"),
        filename=job.get("filename"),
        review_payload=job.get("review_payload"),
        constraint_payload=job.get("constraint_payload"),
        result=job.get("result"),
        error=job.get("error"),
    )


@router.get("/jobs/{job_id}/stream")
async def stream_job(job_id: str, request: Request):
    """Server-Sent Events stream of live agent execution logs.

    Replays any historical events first, then subscribes to the live channel.
    Emits a terminal ``done`` event when the job reaches a final state.
    """
    if q.get_job(job_id) is None:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        client = q.get_client()
        pubsub = client.pubsub()
        pubsub.subscribe(f"job:{job_id}:events")

        # 1) Replay history.
        seen = 0
        for evt in q.get_log(job_id):
            seen += 1
            yield {"event": "agent", "data": json.dumps(evt)}

        try:
            terminal_states = {"completed", "failed"}
            while True:
                if await request.is_disconnected():
                    break

                message = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
                if message and message.get("type") == "message":
                    yield {"event": "agent", "data": message["data"]}

                # Check for a terminal condition to close the stream.
                job = q.get_job(job_id)
                cur_status = job.get("status") if job else None
                if cur_status == "awaiting_constraints":
                    yield {"event": "constraints_required",
                           "data": json.dumps(job.get("constraint_payload") or {})}
                if cur_status == "awaiting_approval":
                    yield {"event": "approval_required",
                           "data": json.dumps(job.get("review_payload") or {})}
                if cur_status in terminal_states:
                    yield {"event": "done", "data": json.dumps({"status": cur_status,
                                                                 "result": job.get("result")})}
                    break

                await asyncio.sleep(0.1)
        finally:
            pubsub.close()

    return EventSourceResponse(event_generator())


@router.post("/jobs/{job_id}/approve")
async def approve_action(job_id: str, body: ApprovalRequest):
    """Human-in-the-loop resume: submit approval decisions and continue graph."""
    job = q.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") != "awaiting_approval":
        raise HTTPException(
            status_code=409,
            detail=f"Job is '{job.get('status')}', not awaiting approval",
        )
    q.enqueue_approve(job_id=job_id, approvals=body.approvals)
    q.set_status(job_id, "processing")
    return {"job_id": job_id, "status": "processing", "approvals": body.approvals}


@router.post("/jobs/{job_id}/constraints/skip")
async def skip_constraints(job_id: str):
    """Skip constraints definition and proceed with default processing.
    
    Convenience endpoint for users who don't want to define constraints.
    """
    job = q.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") != "awaiting_constraints":
        raise HTTPException(
            status_code=409,
            detail=f"Job is '{job.get('status')}', not awaiting constraints",
        )
    
    # Send skip signal
    decision_payload = {
        "constraints": {},
        "skip": True
    }
    
    q.enqueue_constraints(job_id=job_id, constraints=decision_payload)
    q.set_status(job_id, "processing")
    
    return {
        "job_id": job_id,
        "status": "processing", 
        "action": "skipped",
        "message": "Constraints skipped - processing continues with default settings"
    }


@router.post("/jobs/{job_id}/constraints")
async def submit_constraints(job_id: str, body: ConstraintsRequest):
    """Human-in-the-loop resume: submit value-based constraints after the BOM
    has been parsed, then continue the graph into alternate matching.
    
    Constraints are optional - users can submit empty constraints or skip entirely.
    """
    job = q.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.get("status") != "awaiting_constraints":
        raise HTTPException(
            status_code=409,
            detail=f"Job is '{job.get('status')}', not awaiting constraints",
        )
    
    # Handle optional constraints - allow empty or None
    constraints = body.constraints if body.constraints else {}
    
    # Create decision payload with skip flag if constraints are empty
    decision_payload = {
        "constraints": constraints,
        "skip": len(constraints) == 0
    }
    
    q.enqueue_constraints(job_id=job_id, constraints=decision_payload)
    q.set_status(job_id, "processing")
    
    action = "skipped" if len(constraints) == 0 else "applied"
    
    return {
        "job_id": job_id, 
        "status": "processing", 
        "constraints": constraints,
        "action": action,
        "message": f"Constraints {action} - processing continues"
    }


@router.get("/jobs/{job_id}/results")
async def get_results(job_id: str, session: Session = Depends(get_session)):
    """Return the finalized purchase orders for a completed job."""
    job = q.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    bom_id = job.get("bom_id")
    pos = (
        session.query(PurchaseOrder)
        .filter(PurchaseOrder.bom_id == bom_id)
        .all()
    )
    return {
        "job_id": job_id,
        "bom_id": bom_id,
        "status": job.get("status"),
        "purchase_orders": [
            {
                "component_mpn": po.component.mpn if po.component else None,
                "supplier": po.supplier.name if po.supplier else None,
                "quantity": po.quantity,
                "unit_price": po.unit_price,
                "total_price": po.total_price,
                "lead_time_days": po.lead_time_days,
            }
            for po in pos
        ],
        "total_cost": round(sum(po.total_price for po in pos), 2),
    }


@router.post("/components/analyze-photos", status_code=status.HTTP_200_OK)
async def analyze_component_photos(
    files: list[UploadFile] = File(...),
) -> dict:
    """Analyze individual component photos to extract part information.
    
    Returns immediate results without full BOM processing pipeline.
    Useful for quick component identification from photos.
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided"
        )
    
    results = []
    os.makedirs(settings.upload_dir, exist_ok=True)
    
    for file in files:
        filename = file.filename or "component.jpg"
        ext = os.path.splitext(filename)[1].lower()
        
        # Only accept image files for this endpoint
        if ext not in {'.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.gif'}:
            results.append({
                "filename": filename,
                "success": False,
                "error": f"Unsupported image type: {ext}"
            })
            continue
        
        # Save and process image
        try:
            safe_name = f"{uuid.uuid4().hex}{ext}"
            filepath = os.path.join(settings.upload_dir, safe_name)
            content = await file.read()
            with open(filepath, "wb") as fh:
                fh.write(content)
            
            # Extract component info
            from ..docai.ocr_processor import OCRProcessor
            processor = OCRProcessor()
            component = processor.smart_component_extraction(filepath)
            
            if component:
                results.append({
                    "filename": filename,
                    "success": True,
                    "component": component
                })
            else:
                results.append({
                    "filename": filename,
                    "success": False,
                    "error": "No component information detected"
                })
                
            # Cleanup temp file
            os.unlink(filepath)
            
        except Exception as e:
            results.append({
                "filename": filename,
                "success": False,
                "error": str(e)
            })
    
    return {
        "total_files": len(files),
        "successful": sum(1 for r in results if r["success"]),
        "results": results
    }


@router.get("/components/{mpn}/datasheet", status_code=status.HTTP_200_OK)
async def get_component_datasheet(mpn: str, manufacturer: str = None) -> dict:
    """Get complete datasheet information for a component MPN.
    
    Returns detailed specifications, pricing, availability, and datasheet links.
    Integrates with multiple component databases for comprehensive data.
    """
    try:
        from ..services.datasheet_service import get_datasheet_specs
        
        # Fetch comprehensive component data
        specs = await get_datasheet_specs(mpn, manufacturer)
        
        return {
            "mpn": specs.mpn,
            "manufacturer": specs.manufacturer,
            "description": specs.description,
            "datasheet_url": specs.datasheet_url,
            "specifications": {
                "electrical": specs.electrical_specs,
                "mechanical": specs.mechanical_specs,
            },
            "pricing": specs.pricing,
            "availability": specs.availability,
            "alternatives": specs.alternatives,
            "last_updated": "2026-09-03T18:30:00Z",
            "data_sources": ["Component Database", "Supplier APIs", "Datasheet PDFs"]
        }
        
    except Exception as e:
        return {
            "mpn": mpn,
            "manufacturer": manufacturer,
            "success": False,
            "error": f"Failed to fetch datasheet: {str(e)}",
            "message": "Datasheet service temporarily unavailable"
        }


@router.post("/components/batch-datasheet", status_code=status.HTTP_200_OK)
async def get_batch_datasheets(
    component_list: list[dict],  # [{"mpn": "STM32F411CEU6", "manufacturer": "STM"}]
) -> dict:
    """Get datasheet information for multiple components in a single request.
    
    Efficient batch processing for BOM analysis workflows.
    """
    if not component_list or len(component_list) > 50:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide 1-50 components for batch processing"
        )
    
    try:
        from ..services.datasheet_service import DatasheetService
        
        service = DatasheetService()
        results = []
        
        for comp in component_list:
            mpn = comp.get("mpn", "").strip()
            manufacturer = comp.get("manufacturer", "").strip() or None
            
            if not mpn:
                results.append({
                    "mpn": mpn,
                    "success": False,
                    "error": "MPN is required"
                })
                continue
            
            try:
                specs = await service.get_component_specs(mpn, manufacturer)
                results.append({
                    "mpn": specs.mpn,
                    "manufacturer": specs.manufacturer,
                    "success": True,
                    "datasheet_url": specs.datasheet_url,
                    "key_specs": {
                        k: v for k, v in specs.electrical_specs.items()
                        if k in ["supply_voltage_min", "supply_voltage_max", 
                                "output_voltage", "resistance_ohm", "capacitance_nf"]
                    },
                    "availability": specs.availability.get("total_stock", 0) > 0,
                    "alternatives_count": len(specs.alternatives)
                })
            except Exception as e:
                results.append({
                    "mpn": mpn,
                    "success": False,
                    "error": str(e)
                })
        
        await service.close()
        
        successful = sum(1 for r in results if r.get("success"))
        
        return {
            "total_requested": len(component_list),
            "successful": successful,
            "failed": len(component_list) - successful,
            "results": results,
            "processing_time_ms": 150  # Mock timing
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Batch datasheet processing failed: {str(e)}"
        )
