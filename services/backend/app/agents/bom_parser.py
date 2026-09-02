"""Agent 1 — BOM Parser: takes the uploaded file, runs Document AI extraction,
and populates ``state["line_items"]`` with structured component rows."""
from __future__ import annotations

from ..docai.parser import parse_bom_file
from .events import emit
from .state import WorkflowState


def bom_parser_node(state: WorkflowState) -> dict:
    """LangGraph node: parse the uploaded BOM file(s) into line items."""
    job_id = state["job_id"]
    filepath = state["filepath"]
    batch_files = state.get("batch_files", [])
    events = list(state.get("events", []))

    events.append(emit(job_id, "BOM Parser", "start", {
        "filepath": filepath, 
        "batch_mode": len(batch_files) > 1,
        "total_files": len(batch_files) if batch_files else 1
    }))

    try:
        if batch_files and len(batch_files) > 1:
            # Use hybrid parser for multiple files
            from ..docai.hybrid_parser import parse_hybrid_bom
            rows = parse_hybrid_bom(batch_files)
            events.append(emit(job_id, "BOM Parser", "hybrid_processing", {
                "files_processed": len(batch_files),
                "components_found": len(rows)
            }))
        else:
            # Single file processing
            rows = parse_bom_file(filepath)
    except Exception as exc:
        events.append(emit(job_id, "BOM Parser", "error", {"error": str(exc)}))
        return {"line_items": [], "events": events, "error": str(exc)}

    # Normalise into LineItemState dicts
    line_items = []
    for row in rows:
        line_items.append({
            "line_number": row["line_number"],
            "reference_designator": row.get("reference_designator", ""),
            "mpn": row["mpn"],
            "quantity": row.get("quantity", 1),
            "description": row.get("description", ""),
            "component_id": None,
            "is_in_stock": None,
            "alternate_component_id": None,
            "alternate_mpn": None,
            "alternate_manufacturer": None,
            "alternate_description": None,
            "alternate_score": None,
            "needs_approval": False,
            "alternate_approved": None,
            "po_supplier": None,
            "po_unit_price": None,
            "po_total_price": None,
            "po_lead_time_days": None,
            # Multi-modal metadata
            "source_type": row.get("source_type", "unknown"),
            "source_file": row.get("source_file", ""),
            "confidence": row.get("confidence", 1.0),
            "component_type": row.get("component_type"),
            "additional_sources": row.get("additional_sources", []),
        })

    events.append(emit(job_id, "BOM Parser", "complete", {"parsed_lines": len(line_items)}))
    return {"line_items": line_items, "events": events}
