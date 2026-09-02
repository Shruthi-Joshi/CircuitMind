"""Pydantic request/response schemas for the API."""
from __future__ import annotations

from pydantic import BaseModel, Field


class AnalyzeResponse(BaseModel):
    """Returned immediately (HTTP 202) after a BOM upload."""
    job_id: str
    bom_id: str
    status: str = "queued"
    message: str = "BOM accepted for processing"


class ApprovalRequest(BaseModel):
    """Human-in-the-loop decision payload.

    ``approvals`` maps original (out-of-stock) MPN → approve (True) / reject.
    """
    approvals: dict[str, bool] = Field(default_factory=dict)


class ConstraintsRequest(BaseModel):
    """Human-defined value-based constraints submitted after BOM parsing.

    ``constraints`` maps a parameter key to a concrete target value, e.g.
    ``{"package": "LQFP-48", "voltage_max": 3.3, "pin_count": 48}``. Unknown
    keys and un-coercible values are dropped server-side.
    """
    constraints: dict = Field(default_factory=dict)


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    filename: str | None = None
    review_payload: dict | None = None
    constraint_payload: dict | None = None
    result: dict | None = None
    error: str | None = None
