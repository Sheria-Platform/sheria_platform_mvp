# services/api/app/agents/state.py
"""LangGraph agent state definition.

The ``AgentState`` TypedDict is the single shared data structure passed
between every node in the LangGraph workflow.  Each node receives a copy
of the current state and returns a dict of keys to *update* (not replace)
in the next state.

The ``Annotated[list, operator.add]`` pattern on ``messages`` causes
LangGraph to *append* new messages rather than overwrite the entire list,
which preserves the full conversation history across nodes.

Example:
    >>> state = AgentState(
    ...     messages=[{"role": "user", "content": "Hello"}],
    ...     documents=[],
    ...     current_query="Hello",
    ...     plan=[],
    ...     action="direct_answer",
    ...     tool_choice="",
    ...     tool_input="",
    ... )
"""

import operator
from typing import Annotated, TypedDict


class AgentState(TypedDict):
    """Typed state object passed between nodes in the LangGraph workflow.

    All fields are plain Python types so they can be serialised and
    compared by LangGraph.  Optional fields default to empty strings /
    lists when not set by a node.

    Attributes:
        messages: Full conversation history as a list of
            ``{"role": str, "content": str}`` dicts.  Uses
            ``operator.add`` so new messages are **appended**.
        documents: Retrieved context strings from Qdrant and Neo4j,
            injected by the retriever node.
        current_query: The (possibly refined) query being processed
            in the current turn; set by the planner node.
        plan: Planner scratchpad — a list of reasoning strings
            accumulated across planning steps.
        action: Routing decision from the planner:
            ``"retrieve"``, ``"direct_answer"``, or ``"tool_use"``.
        tool_choice: Name of the tool to invoke when
            ``action == "tool_use"`` (e.g. ``"calculator"``).
        tool_input: Raw string input passed to the selected tool.
        web_search_enabled: When True, the planner system prompt is augmented
            to include ``"web_search"`` as an available tool_choice, allowing
            the agent to fetch live results from https://new.kenyalaw.org/.
            Set from ``ChatRequest.web_search``. Defaults to False.
    """

    messages: Annotated[list[dict], operator.add]
    documents: list[str]
    current_query: str
    plan: list[str]
    # Planner routing decision
    action: str
    # Tool node inputs
    tool_choice: str
    tool_input: str
    # Embedding computed at cache-check time; reused by retriever to avoid re-embedding
    query_vector: list[float]
    # Optional court filter for the legal-research route (e.g. ["Supreme Court", "Court of Appeal"])
    # Empty list means no filter — return results from all courts.
    jurisdiction_filter: list[str]
    # Structured citations extracted by the retriever for the legal-research response
    citations: list[dict]
    # Set from ChatRequest.web_search; gates web search routing in the planner prompt
    web_search_enabled: bool
