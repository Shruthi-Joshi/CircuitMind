"""Agent 5 — PO Generator: for every resolved line item (in-stock original OR
approved alternate), run multi-vendor arbitrage to pick the lowest-cost /
lowest-lead-time supplier, then persist split purchase orders + audit logs."""
from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from ..db.models import (
    AuditLog,
    BOM,
    BOMLineItem,
    PurchaseOrder,
    SupplierStock,
)
from ..db.session import SessionLocal
from .events import emit
from .state import WorkflowState


def _best_stock(session: Session, component_id, quantity: int) -> SupplierStock | None:
    """Pick the best in-stock supplier: lowest unit price with enough qty,
    tie-broken by shortest lead time."""
    rows = (
        session.query(SupplierStock)
        .filter(
            SupplierStock.component_id == component_id,
            SupplierStock.is_in_stock == True,  # noqa: E712
            SupplierStock.quantity_available >= quantity,
        )
        .all()
    )
    if not rows:
        # Fall back to any in-stock entry (partial fulfilment)
        rows = (
            session.query(SupplierStock)
            .filter(
                SupplierStock.component_id == component_id,
                SupplierStock.is_in_stock == True,  # noqa: E712
                SupplierStock.quantity_available > 0,
            )
            .all()
        )
    if not rows:
        return None
    return min(rows, key=lambda s: (s.unit_price, s.lead_time_days))


def po_generator_node(state: WorkflowState) -> dict:
    """LangGraph node: generate split purchase orders and persist everything."""
    job_id = state["job_id"]
    bom_id = state.get("bom_id")
    line_items: list[dict] = list(state.get("line_items", []))
    events = list(state.get("events", []))

    events.append(emit(job_id, "PO Generator", "start", {"items": len(line_items)}))

    session: Session = SessionLocal()
    total_cost = 0.0
    po_count = 0
    try:
        # Map parsed line items back to DB rows for FK integrity.
        db_line_items = {
            li.line_number: li
            for li in session.query(BOMLineItem).filter(BOMLineItem.bom_id == bom_id).all()
        } if bom_id else {}

        for item in line_items:
            # Decide which component to purchase.
            purchase_component_id = None
            using_alternate = False

            if item.get("is_in_stock") and item.get("component_id"):
                purchase_component_id = item["component_id"]
            elif item.get("needs_approval") and item.get("alternate_approved") and item.get("alternate_component_id"):
                purchase_component_id = item["alternate_component_id"]
                using_alternate = True
            else:
                # No stock and no approved alternate — skip, record audit.
                session.add(AuditLog(
                    bom_id=bom_id,
                    agent_name="PO Generator",
                    action="skipped_unresolved",
                    detail={"mpn": item["mpn"], "reason": "no stock / alternate not approved"},
                ))
                events.append(emit(job_id, "PO Generator", "skipped", {"mpn": item["mpn"]}))
                continue

            best = _best_stock(session, purchase_component_id, item["quantity"])
            if best is None:
                events.append(emit(job_id, "PO Generator", "no_supplier", {"mpn": item["mpn"]}))
                continue

            qty = item["quantity"]
            line_total = round(best.unit_price * qty, 4)
            total_cost += line_total
            po_count += 1

            # Persist PO row.
            db_li = db_line_items.get(item["line_number"])
            po = PurchaseOrder(
                bom_id=bom_id,
                bom_line_item_id=db_li.id if db_li else None,
                component_id=purchase_component_id,
                supplier_id=best.supplier_id,
                quantity=qty,
                unit_price=best.unit_price,
                total_price=line_total,
                lead_time_days=best.lead_time_days,
            )
            session.add(po)

            # Reflect chosen supplier in state for the UI.
            supplier_name = best.supplier.name if best.supplier else str(best.supplier_id)
            item["po_supplier"] = supplier_name
            item["po_unit_price"] = best.unit_price
            item["po_total_price"] = line_total
            item["po_lead_time_days"] = best.lead_time_days

            # Update DB line item resolution.
            if db_li is not None:
                db_li.is_in_stock = item.get("is_in_stock")
                db_li.component_id = item.get("component_id")
                db_li.alternate_component_id = item.get("alternate_component_id")
                db_li.alternate_score = item.get("alternate_score")
                db_li.alternate_approved = item.get("alternate_approved")

            session.add(AuditLog(
                bom_id=bom_id,
                agent_name="PO Generator",
                action="po_created",
                detail={
                    "mpn": item["mpn"],
                    "purchased_mpn": item.get("alternate_mpn") if using_alternate else item["mpn"],
                    "using_alternate": using_alternate,
                    "supplier": supplier_name,
                    "quantity": qty,
                    "unit_price": best.unit_price,
                    "total_price": line_total,
                    "lead_time_days": best.lead_time_days,
                },
            ))

            events.append(emit(job_id, "PO Generator", "po_created", {
                "mpn": item.get("alternate_mpn") if using_alternate else item["mpn"],
                "supplier": supplier_name,
                "quantity": qty,
                "total_price": line_total,
                "using_alternate": using_alternate,
            }))

        # Mark BOM completed.
        if bom_id:
            bom = session.get(BOM, bom_id)
            if bom:
                bom.status = "completed"
                bom.completed_at = datetime.datetime.now(datetime.timezone.utc)

        session.commit()
    except Exception as exc:
        session.rollback()
        events.append(emit(job_id, "PO Generator", "error", {"error": str(exc)}))
        session.close()
        return {"line_items": line_items, "events": events, "error": str(exc)}
    finally:
        session.close()

    events.append(emit(job_id, "PO Generator", "complete", {
        "purchase_orders": po_count,
        "total_cost": round(total_cost, 2),
    }))

    return {"line_items": line_items, "events": events}
