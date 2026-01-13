# services/api/app/agents/state.py
import operator
from typing import Annotated, TypedDict


class AgentState(TypedDict):
    """
    The state object passed between nodes in the LangGraph.
    Tracks the conversation history and current step data.
    """

    # Using 'operator.add' means new messages are appended, not overwritten
    messages: Annotated[list[dict], operator.add]

    # Context retrieved from RAG (Vector + Graph)
    documents: list[str]

    # The current question being processed
    current_query: str

    # Internal scratchpad for the planner
    plan: list[str]
