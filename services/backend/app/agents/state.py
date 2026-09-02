"""Shared state schema for the LangGraph BOM-processing workflow.

Every node reads from / writes to this TypedDict. The ``events`` list is
an append-only execution log streamed to the frontend via SSE.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, TypedDict


class AgentEvent(TypedDict, total=False):
    """One entry in the real-time execution log sent to the UI."""
    agent: str
    action: str
    detail: dict[str, Any]
    ts: str  # ISO-8601


class LineItemState(TypedDict, total=False):
    """Per-component processing result that accumulates across agents."""
    line_number: int
    reference_designator: str
    mpn: str
    quantity: int
    description: str

    # Set by Market Check agent
    component_id: str | None
    is_in_stock: bool | None

    # Set by Alternate Match agent
    alternate_component_id: str | None
    alternate_mpn: str | None
    alternate_manufacturer: str | None
    alternate_description: str | None
    alternate_score: float | None
    needs_approval: bool

    # Set by Human Approval Gate / resume
    alternate_approved: bool | None

    # Set by PO Generator
    po_supplier: str | None
    po_unit_price: float | None
    po_total_price: float | None
    po_lead_time_days: int | None


class WorkflowState(TypedDict, total=False):
    """Top-level state for the LangGraph BOM-processing graph."""

    # Identifiers
    job_id: str
    bom_id: str
    filepath: str
    # User-defined non-negotiables (value-based): {key: value} thresholds,
    # e.g. {"package": "LQFP-48", "voltage_max": 3.3, "pin_count": 48}.
    # Populated by the constraint_gate interrupt node from human input.
    critical_constraints: dict[str, Any]
    needs_constraint_input: bool
    constraints_received: bool
    needs_human_approval: bool
    events: list[dict]

    # Parsed BOM lines (populated by BOM Parser agent)
    line_items: list[LineItemState]

    # Items that need human review (subset of line_items with alternates)
    items_needing_approval: list[LineItemState]

    # Flags
    needs_human_approval: bool
    approval_received: bool

    # Running event log (append-only)
    events: list[AgentEvent]

    # Error tracking
    error: str | None