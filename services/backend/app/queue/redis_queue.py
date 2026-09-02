"""Redis-backed task queue + job state store + event pub/sub.

Design
------
- ``enqueue_process`` / ``enqueue_approve`` push JSON commands onto a single
  Redis list ("bom-processing-queue"). The worker pops with BRPOP.
- Job metadata (status, review payload, result) is stored in a Redis hash
  ``job:{id}:meta`` so the API can answer status queries statelessly.
- Live agent events are published on ``job:{id}:events`` (see agents/events.py)
  and mirrored into a Redis list ``job:{id}:log`` for replay on reconnect.
"""
from __future__ import annotations

import json
import time
import uuid
from typing import Any

import redis

from ..config import settings

_client: redis.Redis | None = None


def get_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    return _client


# ── Queue commands ────────────────────────────────────────────────────────────

def enqueue_process(job_id: str, bom_id: str, filepath: str,
                    constraints: list[str] | None = None, 
                    bypass_constraints: bool = False,
                    batch_files: list[str] | None = None) -> None:
    payload = {
        "type": "process",
        "job_id": job_id,
        "bom_id": bom_id,
        "filepath": filepath,
        "constraints": constraints or [],
        "bypass_constraints": bypass_constraints,
        "batch_files": batch_files or [],
    }
    get_client().lpush(settings.bom_queue, json.dumps(payload))


def enqueue_approve(job_id: str, approvals: dict[str, bool]) -> None:
    payload = {"type": "approve", "job_id": job_id, "approvals": approvals}
    get_client().lpush(settings.bom_queue, json.dumps(payload))


def enqueue_constraints(job_id: str, constraints: dict[str, Any]) -> None:
    """Resume a constraints-interrupted job with the user's value thresholds."""
    payload = {"type": "constraints", "job_id": job_id, "constraints": constraints}
    get_client().lpush(settings.bom_queue, json.dumps(payload))


def dequeue(timeout: int = 5) -> dict[str, Any] | None:
    """Blocking pop used by the worker. Returns None on timeout.

    ``BRPOP`` blocks up to ``timeout`` seconds. On an empty queue some
    redis-py/redis combinations surface the server-side blocking timeout as a
    socket ``TimeoutError`` instead of a nil reply. Either way an empty poll is
    not an error for the worker loop, so both are normalised to ``None`` so the
    worker keeps polling instead of crashing every ``timeout`` seconds.
    """
    try:
        result = get_client().brpop(settings.bom_queue, timeout=timeout)
    except redis.exceptions.TimeoutError:
        return None
    if result is None:
        return None
    _, raw = result
    return json.loads(raw)


# ── Job metadata ────────────────────────────────────────────────────────────

def _meta_key(job_id: str) -> str:
    return f"job:{job_id}:meta"


def create_job(filename: str, bom_id: str, bypass_constraints: bool = False) -> str:
    job_id = str(uuid.uuid4())
    get_client().hset(_meta_key(job_id), mapping={
        "job_id": job_id,
        "bom_id": bom_id,
        "filename": filename,
        "status": "queued",
        "created_at": str(time.time()),
        "bypass_constraints": str(bypass_constraints),
    })
    return job_id


def set_status(job_id: str, status: str, **extra: Any) -> None:
    mapping = {"status": status}
    for k, v in extra.items():
        mapping[k] = v if isinstance(v, str) else json.dumps(v)
    get_client().hset(_meta_key(job_id), mapping=mapping)


def get_job(job_id: str) -> dict[str, Any] | None:
    data = get_client().hgetall(_meta_key(job_id))
    if not data:
        return None
    # Decode JSON-encoded fields if present.
    for field in ("review_payload", "result", "constraint_payload"):
        if field in data:
            try:
                data[field] = json.loads(data[field])
            except (json.JSONDecodeError, TypeError):
                pass
    return data


# ── Event log persistence (for SSE replay) ────────────────────────────────────

def append_log(job_id: str, event: dict) -> None:
    get_client().rpush(f"job:{job_id}:log", json.dumps(event))
    get_client().expire(f"job:{job_id}:log", 3600)


def get_log(job_id: str) -> list[dict]:
    raw = get_client().lrange(f"job:{job_id}:log", 0, -1)
    return [json.loads(r) for r in raw]


def publish_event(job_id: str, event: dict) -> None:
    """Publish live + persist for replay."""
    get_client().publish(f"job:{job_id}:events", json.dumps(event))
    append_log(job_id, event)
