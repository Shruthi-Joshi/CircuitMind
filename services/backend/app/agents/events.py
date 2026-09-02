"""Thin helper for emitting execution-log events from agent nodes.

Each event is:
1. Appended to the in-memory ``state["events"]`` list (returned to LangGraph).
2. Published to a Redis Pub/Sub channel so the SSE router can push it live.

The Redis publish is fire-and-forget; if Redis is unavailable the agent
continues without error.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import redis

from ..config import settings

_redis: redis.Redis | None = None


def _get_redis() -> redis.Redis | None:
    global _redis
    if _redis is not None:
        return _redis
    try:
        _redis = redis.Redis.from_url(settings.redis_url)
        _redis.ping()
        return _redis
    except Exception:
        _redis = None
        return None


def make_event(
    agent: str,
    action: str,
    detail: dict[str, Any] | None = None,
) -> dict:
    return {
        "agent": agent,
        "action": action,
        "detail": detail or {},
        "ts": datetime.now(timezone.utc).isoformat(),
    }


def emit(job_id: str, agent: str, action: str, detail: dict[str, Any] | None = None) -> dict:
    """Create an event dict, publish it to Redis pub/sub, and persist to the
    per-job log list so late SSE subscribers can replay history."""
    evt = make_event(agent, action, detail)
    r = _get_redis()
    if r is not None:
        try:
            payload = json.dumps(evt)
            r.publish(f"job:{job_id}:events", payload)
            r.rpush(f"job:{job_id}:log", payload)
            r.expire(f"job:{job_id}:log", 3600)
        except Exception:
            pass  # non-critical
    return evt
