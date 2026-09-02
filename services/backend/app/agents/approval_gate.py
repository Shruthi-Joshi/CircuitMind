"""Agent 4 — Human Approval Gate: pauses graph execution using LangGraph's
``interrupt`` primitive when out-of-stock alternates require human sign-off.

When the graph resumes (via ``Command(resume=...)``), the human decision is
merged back into the line items. The frontend supplies a mapping of
``{original_mpn: bool}`` approvals.
"""
from __future__ import annotations

from langgraph.types import interrupt

from .events import emit
from .state import WorkflowState


def approval_gate_node(state: WorkflowState) -> dict:
    """LangGraph node: interrupt for human-in-the-loop approval.

    On first pass, this raises ``interrupt(...)`` which suspends the graph and
    checkpoints state. The API surfaces the payload to the UI. When resumed,
    ``interrupt`` returns the human decision dict and execution continues here.
    """
    job_id = state["job_id"]
    items = state.get("items_needing_approval", [])
    events = list(state.get("events", []))

    # Build the comparison payload shown in the UI's approval modal.
    review_payload = {
        "job_id": job_id,
        "items": [
            {
                "line_number": it["line_number"],
                "reference_designator": it.get("reference_designator", ""),
                "original_mpn": it["mpn"],
                "original_description": it.get("description", ""),
                "quantity": it["quantity"],
                "alternate_mpn": it.get("alternate_mpn"),
                "alternate_manufacturer": it.get("alternate_manufacturer"),
                "alternate_description": it.get("alternate_description"),
                "compatibility_score": it.get("alternate_score"),
            }
            for it in items
        ],
    }

    events.append(emit(job_id, "Human Approval Gate", "awaiting_approval", {
        "items_pending": len(items),
    }))

    # Suspend execution. `decision` is filled when the graph is resumed.
    decision = interrupt(review_payload)

    # ── Resumed from here ────────────────────────────────────────────────
    # `decision` is expected to be {"approvals": {mpn: bool, ...}}
    approvals: dict[str, bool] = {}
    if isinstance(decision, dict):
        approvals = decision.get("approvals", {}) or {}

    line_items = list(state.get("line_items", []))
    approved_count = 0
    for item in line_items:
        if item.get("needs_approval"):
            approved = bool(approvals.get(item["mpn"], False))
            item["alternate_approved"] = approved
            if approved:
                approved_count += 1

    events.append(emit(job_id, "Human Approval Gate", "approval_received", {
        "approved": approved_count,
        "rejected": len(items) - approved_count,
    }))

    return {
        "line_items": line_items,
        "approval_received": True,
        "events": events,
    }
