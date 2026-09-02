"""Background worker (Member 3 + 5): pulls jobs from the Redis queue and
drives the LangGraph multi-agent engine, honouring interrupt/resume for the
human approval gate.

Run with: ``python -m app.worker``

Because LangGraph's MemorySaver checkpoint lives in-process, both the initial
``process`` command and the follow-up ``approve`` command are handled by this
same long-running worker process.
"""
from __future__ import annotations

import time

from langgraph.types import Command

from .agents.graph import get_compiled_graph, run_config
from .db.init_db import init_db
from .db.seed import seed_if_empty
from .queue import redis_queue as q


def _run_graph(job_id: str, initial_state: dict) -> None:
    """Invoke the graph; if it interrupts, store the review payload and stop."""
    graph = get_compiled_graph()
    cfg = run_config(job_id)

    result = graph.invoke(initial_state, config=cfg)
    _handle_result(job_id, graph, cfg, result)


def _resume_graph(job_id: str, approvals: dict) -> None:
    """Resume a previously interrupted graph with the human decision."""
    graph = get_compiled_graph()
    cfg = run_config(job_id)

    result = graph.invoke(Command(resume={"approvals": approvals}), config=cfg)
    _handle_result(job_id, graph, cfg, result)


def _resume_constraints(job_id: str, constraints: dict) -> None:
    """Resume a constraints-interrupted graph with the user's value thresholds."""
    graph = get_compiled_graph()
    cfg = run_config(job_id)

    result = graph.invoke(Command(resume={"constraints": constraints}), config=cfg)
    _handle_result(job_id, graph, cfg, result)


def _is_constraints_interrupt(payload) -> bool:
    """Distinguish the constraints interrupt from the approval interrupt by
    payload shape. The constraints payload carries ``allowed_constraints``;
    the approval payload carries ``items`` (alternates awaiting sign-off)."""
    return isinstance(payload, dict) and "allowed_constraints" in payload


def _handle_result(job_id: str, graph, cfg, result: dict) -> None:
    """Inspect graph state to detect an interrupt vs completion."""
    snapshot = graph.get_state(cfg)
    interrupted = bool(getattr(snapshot, "next", None))

    # LangGraph surfaces pending interrupts via __interrupt__ in the result.
    interrupt_payload = None
    if isinstance(result, dict) and "__interrupt__" in result:
        intr = result["__interrupt__"]
        if intr:
            interrupt_payload = getattr(intr[0], "value", None)

    if interrupt_payload is not None:
        if _is_constraints_interrupt(interrupt_payload):
            q.set_status(job_id, "awaiting_constraints",
                         constraint_payload=interrupt_payload)
            print(f"[worker] job {job_id} awaiting constraints "
                  f"({len(interrupt_payload.get('line_items', []))} line items)")
        else:
            q.set_status(job_id, "awaiting_approval", review_payload=interrupt_payload)
            print(f"[worker] job {job_id} awaiting human approval "
                  f"({len(interrupt_payload.get('items', []))} items)")
        return

    if interrupted:
        # Interrupted but payload not in result — infer from the pending node.
        pending = getattr(snapshot, "next", None) or ()
        if "constraint_gate" in pending:
            q.set_status(job_id, "awaiting_constraints")
            print(f"[worker] job {job_id} interrupted (awaiting constraints)")
        else:
            q.set_status(job_id, "awaiting_approval")
            print(f"[worker] job {job_id} interrupted (awaiting approval)")
        return

    # Completed.
    summary = _summarize(result)
    q.set_status(job_id, "completed", result=summary)
    print(f"[worker] job {job_id} completed: {summary['purchase_orders']} POs, "
          f"${summary['total_cost']}")


def _summarize(state: dict) -> dict:
    line_items = state.get("line_items", [])
    pos = [li for li in line_items if li.get("po_supplier")]
    total = round(sum(li.get("po_total_price") or 0.0 for li in pos), 2)
    return {
        "total_line_items": len(line_items),
        "purchase_orders": len(pos),
        "total_cost": total,
        "alternates_used": sum(1 for li in line_items if li.get("alternate_approved")),
        "line_items": line_items,
    }


def handle_command(cmd: dict) -> None:
    ctype = cmd.get("type")
    job_id = cmd.get("job_id")
    if not job_id:
        return

    try:
        if ctype == "process":
            q.set_status(job_id, "processing")
            initial_state = {
                "job_id": job_id,
                "bom_id": cmd["bom_id"],
                "filepath": cmd["filepath"],
                "critical_constraints": cmd.get("constraints", {}) or {},
                "constraints_received": False,
                "bypass_constraints": cmd.get("bypass_constraints", False),
                "batch_files": cmd.get("batch_files", []),
                "line_items": [],
                "items_needing_approval": [],
                "needs_human_approval": False,
                "approval_received": False,
                "events": [],
                "error": None,
            }
            _run_graph(job_id, initial_state)
        elif ctype == "constraints":
            q.set_status(job_id, "processing")
            _resume_constraints(job_id, cmd.get("constraints", {}))
        elif ctype == "approve":
            q.set_status(job_id, "processing")
            _resume_graph(job_id, cmd.get("approvals", {}))
        else:
            print(f"[worker] unknown command type: {ctype}")
    except Exception as exc:  # keep the worker alive on job failure
        import traceback
        traceback.print_exc()
        q.set_status(job_id, "failed", error=str(exc))


def main() -> None:
    print("[worker] starting CircuitMind agent worker ...")
    # Ensure schema + seed exist (idempotent) before processing.
    for attempt in range(30):
        try:
            init_db()
            seed_if_empty()
            break
        except Exception as exc:
            print(f"[worker] waiting for DB ({attempt + 1}/30): {exc}")
            time.sleep(2)

    print("[worker] ready — polling queue")
    while True:
        cmd = q.dequeue(timeout=5)
        if cmd is None:
            continue
        print(f"[worker] got command: {cmd.get('type')} job={cmd.get('job_id')}")
        handle_command(cmd)


if __name__ == "__main__":
    main()
