# services/api/app/agents/nodes/planner.py
"""LangGraph Planner node.

Analyses the latest user message and decides how the rest of the graph
should proceed.  The planner calls the Ollama LLM with a structured
prompt and parses the JSON response to extract:

- ``action``        — routing decision for the conditional edge.
- ``refined_query`` — standalone search query (coreferences resolved).
- ``reasoning``     — scratchpad text stored in ``state["plan"]``.

The node is deterministic (``temperature=0.0``) and uses ``json_mode``
to guarantee a parseable response.  On any failure it falls back to
``action="retrieve"`` so the pipeline always progresses.

Example:
    The planner transforms:
        "What did the court decide in that case about land?"
    Into:
        ``refined_query`` = "court decision adverse possession Kenya"
        ``action``        = "retrieve"
"""

import json
import logging
import time

from services.api.app.agents.state import AgentState
from services.api.app.clients.ollama_client import ollama_client

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """
You are a Judicial Research Planning Agent for Kenya's Sheria Platform.
You assist judges, magistrates, registrars, and court staff with legal research queries.

Analyze the user's query and conversation history. Decide the next action:

1. "direct_answer"  — Greetings, simple clarifications, or questions answerable
                       without retrieving documents (e.g. "Hello", "What can you
                       help me with?", "Thank you").

2. "retrieve"       — Any legal research question requiring case law, statutes,
                       or court records:
                       - Case law search ("What is the test for adverse possession?")
                       - Statutory interpretation ("What does Section 26 of the
                         Land Registration Act provide?")
                       - Precedent lookup ("Find Court of Appeal cases on vicarious
                         liability in medical negligence")
                       - Judgment drafting assistance or citation validation

3. "tool_use"       — Requests requiring computation or structured external data:
                       - Case duration prediction or delay risk assessment
                       - Judge workload analytics
                       - Document authenticity verification (court orders, title deeds)
                       - Mathematical or statistical calculations

When writing "refined_query":
- Resolve coreferences using conversation history ("that case" → full case name and citation)
- Preserve Kenya Law citation format exactly: [Year] KESC / KECA / KEHC Number
- Preserve legal Latin terms verbatim (mens rea, ratio decidendi, obiter dicta, locus standi)
- Include court name and jurisdiction tier when mentioned
- Include date ranges when legally relevant to the search

Output JSON ONLY — no prose, no markdown:
{
    "action": "retrieve" | "direct_answer" | "tool_use",
    "refined_query": "Standalone, self-contained legal search query",
    "legal_domain": "land_law|criminal|family|constitutional|commercial|procedural|other",
    "reasoning": "Brief explanation of routing decision"
}
"""


async def planner_node(state: AgentState) -> dict:
    """Analyse the user query and decide the next graph step.

    Calls Ollama with a structured JSON-mode prompt to classify the
    intent and rewrite the query for retrieval.  The returned dict
    updates ``state["action"]``, ``state["current_query"]``, and
    ``state["plan"]``.

    Args:
        state: Current agent state.  Must contain at least one message
            in ``state["messages"]``.

    Returns:
        A partial state dict with keys:
            - ``"current_query"`` (str): Refined standalone query.
            - ``"plan"`` (list[str]): Single-element list with the
              planner's reasoning text.
            - ``"action"`` (str): One of ``"retrieve"``,
              ``"direct_answer"``, or ``"tool_use"``.

    Note:
        On any exception (LLM unavailable, JSON parse error) the node
        returns ``action="retrieve"`` as a safe default so the graph
        continues rather than crashing.
    """
    logger.info("Planner node started", extra={"node": "planner"})
    start = time.perf_counter()

    last_message = state["messages"][-1]
    user_query: str = (
        last_message.content
        if hasattr(last_message, "content")
        else last_message["content"]
    )

    try:
        # Send last 6 messages (3 turns) so the planner can resolve coreferences
        recent_messages = state["messages"][-6:]
        response_text = await ollama_client.chat_completion(
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                *recent_messages,
            ],
            temperature=0.0,  # deterministic planning
            json_mode=True,   # constrain output to valid JSON
        )

        plan: dict = json.loads(response_text)
        action: str = plan.get("action", "retrieve")
        legal_domain: str = plan.get("legal_domain", "other")
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        logger.info(
            "Planner node completed",
            extra={
                "node": "planner",
                "action": action,
                "legal_domain": legal_domain,
                "duration_ms": duration_ms,
            },
        )

        return {
            "current_query": plan.get("refined_query", user_query),
            "plan": [plan.get("reasoning", "")],
            "action": action,
        }

    except Exception as exc:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.error(
            "Planner node failed, defaulting to retrieve",
            exc_info=True,
            extra={"node": "planner", "duration_ms": duration_ms},
        )
        return {
            "current_query": user_query,
            "plan": ["Error in planning, defaulting to retrieval."],
            "action": "retrieve",
        }
