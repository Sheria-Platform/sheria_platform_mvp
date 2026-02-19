# services/api/app/agents/graph.py
"""LangGraph agentic RAG workflow definition.

Compiles the ``agent_app`` runnable used by the chat route.  The graph
implements a three-stage pipeline with conditional branching after the
planning step:

.. code-block:: text

    ┌──────────┐
    │  Planner │ ── "direct_answer" ──────────────────────┐
    └──────────┘                                           │
         │ "retrieve"                 "tool_use"           │
         ▼                                ▼               ▼
    ┌──────────┐             ┌──────────────┐     ┌───────────┐
    │ Retriever│             │     Tool     │     │ Responder │
    └──────────┘             └──────────────┘     └───────────┘
         │                        │
         └──────────┬─────────────┘
                    ▼
             ┌───────────┐
             │ Responder │
             └───────────┘

The compiled ``agent_app`` is an async iterable; callers use
``async for event in agent_app.astream(state)`` to receive per-node
state updates as they complete.

"""

from langgraph.graph import END, StateGraph

from services.api.app.agents.nodes.planner import planner_node
from services.api.app.agents.nodes.responder import generate_node
from services.api.app.agents.nodes.retriever import retrieve_node
from services.api.app.agents.nodes.tool import tool_node
from services.api.app.agents.state import AgentState


def _route_after_planner(state: AgentState) -> str:
    """Select the next node based on the planner's action decision.

    This function is used as the routing function for the conditional
    edge that follows the planner node.

    Args:
        state: Current agent state containing ``action`` set by the
            planner node.

    Returns:
        One of ``"retriever"``, ``"tool"``, or ``"responder"``.

    Note:
        Any unrecognised ``action`` value defaults to ``"retriever"``
        to prevent the graph from getting stuck.
    """
    action = state.get("action", "retrieve")
    if action == "direct_answer":
        return "responder"
    if action == "tool_use":
        return "tool"
    return "retriever"  # default for "retrieve" and unknown values


# ── Graph Construction ────────────────────────────────────────────────────
_workflow = StateGraph(AgentState)

# Register nodes
_workflow.add_node("planner", planner_node)
_workflow.add_node("retriever", retrieve_node)
_workflow.add_node("tool", tool_node)
_workflow.add_node("responder", generate_node)

# Entry point
_workflow.set_entry_point("planner")

# Conditional branching after planner
_workflow.add_conditional_edges(
    "planner",
    _route_after_planner,
    {
        "retriever": "retriever",
        "tool": "tool",
        "responder": "responder",
    },
)

# Fixed edges: both retriever and tool feed the responder
_workflow.add_edge("retriever", "responder")
_workflow.add_edge("tool", "responder")
_workflow.add_edge("responder", END)

# ── Compiled Application ──────────────────────────────────────────────────
agent_app = _workflow.compile()
"""Compiled LangGraph runnable.  Import this in the chat route."""
