"""LangGraph state machine wiring.

Flow:
    START → bom_parser → constraint_gate → market_check → alternate_match → [route]
    route:
        if needs_human_approval → approval_gate → po_generator → END
        else                    → po_generator → END

Both ``constraint_gate`` and ``approval_gate`` use LangGraph's ``interrupt``
primitive, so the graph pauses and checkpoints there. ``constraint_gate`` fires
right after parsing so the engineer can define value-based non-negotiable
constraints before matching runs. A checkpointer is required for
interrupt/resume; we use an in-memory saver by default (single worker) and
fall back gracefully.
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from ..config import settings
from .alternate_match import alternate_match_node
from .approval_gate import approval_gate_node
from .bom_parser import bom_parser_node
from .constraint_gate import constraint_gate_node
from .market_check import market_check_node
from .po_generator import po_generator_node
from .state import WorkflowState


def _route_after_alternate(state: WorkflowState) -> str:
    """Conditional edge: go to human approval if alternates were found."""
    if state.get("needs_human_approval"):
        return "approval_gate"
    return "po_generator"


def build_graph(checkpointer=None):
    """Construct and compile the LangGraph workflow.

    Parameters
    ----------
    checkpointer:
        A LangGraph checkpointer (e.g. MemorySaver). Required to support
        interrupt/resume. If None, a MemorySaver is created.
    """
    if checkpointer is None:
        from langgraph.checkpoint.memory import MemorySaver

        checkpointer = MemorySaver()

    graph = StateGraph(WorkflowState)

    graph.add_node("bom_parser", bom_parser_node)
    graph.add_node("constraint_gate", constraint_gate_node)
    graph.add_node("market_check", market_check_node)
    graph.add_node("alternate_match", alternate_match_node)
    graph.add_node("approval_gate", approval_gate_node)
    graph.add_node("po_generator", po_generator_node)

    graph.add_edge(START, "bom_parser")
    graph.add_edge("bom_parser", "constraint_gate")
    graph.add_edge("constraint_gate", "market_check")
    graph.add_edge("market_check", "alternate_match")
    graph.add_conditional_edges(
        "alternate_match",
        _route_after_alternate,
        {"approval_gate": "approval_gate", "po_generator": "po_generator"},
    )
    graph.add_edge("approval_gate", "po_generator")
    graph.add_edge("po_generator", END)

    return graph.compile(checkpointer=checkpointer)


# A module-level compiled graph reused by the worker (shares its MemorySaver so
# a resume hits the same checkpoint within the worker process).
_compiled = None


def get_compiled_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph()
    return _compiled


# Convenience: config with the NFR recursion limit applied.
def run_config(job_id: str) -> dict:
    return {
        "configurable": {"thread_id": job_id},
        "recursion_limit": settings.recursion_limit,
    }
