"""Agent 2b — Constraints Gate: pauses the graph right after BOM parsing so the
engineer can define value-based non-negotiable constraints *before* alternate
matching runs.

Using LangGraph's ``interrupt`` primitive, the graph suspends here and
checkpoints. The API surfaces the parsed BOM summary + the selectable parameter
catalog to the UI. When resumed via ``Command(resume=...)`` the user's typed
constraint values are merged into ``critical_constraints`` and matching proceeds.
"""
from __future__ import annotations

from langgraph.types import interrupt

from .alternate_match import ALLOWED_VALUE_CONSTRAINTS, normalize_value_constraints
from .events import emit
from .state import WorkflowState


def constraint_gate_node(state: WorkflowState) -> dict:
    """LangGraph node: interrupt for human-defined value-based constraints.

    On first pass, raises ``interrupt(...)`` with a preview of parsed line items
    and the allowed constraint keys. On resume, ``interrupt`` returns the human
    payload ``{"constraints": {key: value, ...}, "skip": boolean}`` which is normalised and
    written to ``critical_constraints`` for the alternate-match agent.
    
    Users can skip constraint definition by setting skip=true or providing empty constraints.
    """
    job_id = state["job_id"]
    line_items = list(state.get("line_items", []))
    events = list(state.get("events", []))

    # Check if constraints should be bypassed (for demo/testing)
    bypass_constraints = state.get("bypass_constraints", False)
    
    if bypass_constraints:
        events.append(emit(job_id, "Constraints Gate", "bypassed", {
            "reason": "bypass_constraints flag set",
            "line_items": len(line_items),
        }))
        
        return {
            "critical_constraints": {},
            "constraints_received": True,
            "constraints_skipped": True,
            "events": events,
        }

    # Preview payload shown in the constraints modal.
    constraint_payload = {
        "job_id": job_id,
        "allowed_constraints": sorted(ALLOWED_VALUE_CONSTRAINTS),
        "line_items": [
            {
                "line_number": it.get("line_number"),
                "reference_designator": it.get("reference_designator", ""),
                "mpn": it.get("mpn"),
                "quantity": it.get("quantity", 1),
                "description": it.get("description", ""),
            }
            for it in line_items
        ],
        "optional": True,  # Indicate that constraints are optional
        "default_action": "proceed",  # Default action if no constraints provided
        "can_skip": True,  # User can skip this step
    }

    events.append(emit(job_id, "Constraints Gate", "awaiting_constraints", {
        "line_items": len(line_items),
        "optional": True,
        "can_skip": True,
    }))

    # Suspend execution. `decision` is filled when the graph is resumed.
    decision = interrupt(constraint_payload)

    # ── Resumed from here ────────────────────────────────────────────────
    # `decision` is expected to be {"constraints": {key: value, ...}, "skip": boolean}.
    # Handle cases where user skips or provides empty constraints.
    raw: dict = {}
    user_skipped = False
    
    if isinstance(decision, dict):
        # Check if user explicitly skipped constraints
        user_skipped = decision.get("skip", False)
        
        if not user_skipped:
            raw = decision.get("constraints", {}) or {}
        
        # If decision is empty or None, treat as skip
        if not decision or (not decision.get("constraints") and not decision.get("skip")):
            user_skipped = True

    # Normalize constraints (empty if skipped)
    value_constraints = {} if user_skipped else normalize_value_constraints(raw)

    events.append(emit(job_id, "Constraints Gate", "constraints_received", {
        "constraints": value_constraints,
        "count": len(value_constraints),
        "skipped": user_skipped,
        "action": "skipped" if user_skipped else "applied",
    }))

    return {
        "critical_constraints": value_constraints,
        "constraints_received": True,
        "constraints_skipped": user_skipped,
        "events": events,
    }
