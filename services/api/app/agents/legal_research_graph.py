# services/api/app/agents/legal_research_graph.py
"""LangGraph workflow for the dedicated legal-research endpoint.

Skips the planner node entirely — every request goes straight to the
retriever then the responder.  This guarantees that legal research queries
are always grounded in retrieved Kenya Law Reports rather than being
short-circuited to a ``direct_answer``.

.. code-block:: text

    ┌──────────┐     ┌───────────┐
    │ Retriever│────▶│ Responder │────▶ END
    └──────────┘     └───────────┘

The compiled ``legal_research_app`` is imported by the legal-research
route and used identically to ``agent_app`` in the chat route.
"""

from langgraph.graph import END, START, StateGraph

from services.api.app.agents.nodes.responder import generate_node
from services.api.app.agents.nodes.retriever import retrieve_node
from services.api.app.agents.state import AgentState

_workflow = StateGraph(AgentState)

_workflow.add_node("retriever", retrieve_node)
_workflow.add_node("responder", generate_node)

_workflow.add_edge(START, "retriever")
_workflow.add_edge("retriever", "responder")
_workflow.add_edge("responder", END)

legal_research_app = _workflow.compile()
"""Compiled LangGraph runnable for the /api/v1/legal-research route."""
