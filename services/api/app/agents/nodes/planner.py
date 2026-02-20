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

from services.api.app.agents.nodes.constitution import Compass
from services.api.app.agents.state import AgentState
from services.api.app.clients.ollama_client import ollama_client

logger = logging.getLogger(__name__)


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
    logger.info("Planner Node: Analyzing query...")

    last_message = state["messages"][-1]
    user_query: str = (
        last_message.content
        if hasattr(last_message, "content")
        else last_message["content"]
    )

    system_instruction = f"{Compass.IDENTITY['persona']}\n\n{Compass.PLANNER}"

    try:
        response_text = await ollama_client.chat_completion(
            messages=[
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": user_query},
            ],
            temperature=0.0,  # deterministic planning
            json_mode=True,   # constrain output to valid JSON
        )

        plan: dict = json.loads(response_text)
        action: str = plan.get("action", "retrieve")
        refined_query = plan.get("refined_query", user_query)

        logger.info("Plan derived: action=%s", action)

        return {
            "current_query": refined_query,
            "action": action,
            "intent": plan.get("reasoning", "Standard routing"),

            "plan": [f"Action: {action} - {plan.get('reasoning', '')}"]
        }

    except Exception as exc:
        logger.error("Planning failed: %s", exc)
        return {
            "current_query": user_query,
            "plan": ["Error in planning, defaulting to retrieval."],
            "action": "retrieve",
        }
