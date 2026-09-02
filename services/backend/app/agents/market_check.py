"""Agent 2 — Market Check: for each parsed line item, look up the component
in the catalog + supplier_stock tables.  Flag items that are out-of-stock
at all vendors."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..db.models import Component, SupplierStock
from ..db.session import SessionLocal
from .events import emit
from .state import WorkflowState


def market_check_node(state: WorkflowState) -> dict:
    """LangGraph node: check stock across all suppliers for each MPN."""
    job_id = state["job_id"]
    line_items: list[dict] = list(state.get("line_items", []))
    events = list(state.get("events", []))

    events.append(emit(job_id, "Market Check", "start", {"items": len(line_items)}))

    session: Session = SessionLocal()
    try:
        for item in line_items:
            mpn = item["mpn"]

            # Look up component by MPN
            comp = session.query(Component).filter(Component.mpn == mpn).first()
            if comp is None:
                # Unknown MPN — treat as out-of-stock
                item["is_in_stock"] = False
                events.append(emit(job_id, "Market Check", "mpn_not_found", {"mpn": mpn}))
                continue

            item["component_id"] = str(comp.id)

            # Check if any supplier has stock
            stock_rows = (
                session.query(SupplierStock)
                .filter(
                    SupplierStock.component_id == comp.id,
                    SupplierStock.is_in_stock == True,  # noqa: E712
                    SupplierStock.quantity_available > 0,
                )
                .all()
            )

            if stock_rows:
                item["is_in_stock"] = True
                best = min(stock_rows, key=lambda s: s.unit_price)
                events.append(emit(job_id, "Market Check", "in_stock", {
                    "mpn": mpn,
                    "cheapest_price": best.unit_price,
                    "suppliers_available": len(stock_rows),
                }))
            else:
                item["is_in_stock"] = False
                events.append(emit(job_id, "Market Check", "out_of_stock", {"mpn": mpn}))
    finally:
        session.close()

    events.append(emit(job_id, "Market Check", "complete", {
        "in_stock": sum(1 for i in line_items if i.get("is_in_stock")),
        "out_of_stock": sum(1 for i in line_items if not i.get("is_in_stock")),
    }))

    return {"line_items": line_items, "events": events}
