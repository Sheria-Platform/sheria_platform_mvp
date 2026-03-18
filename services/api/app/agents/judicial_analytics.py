# services/api/app/agents/judicial_analytics.py
"""Dedicated LangGraph analytics agent for Sheria Predict.

Handles multi-step judicial analytics queries (workload analysis, delay risk
assessment, multi-case comparisons) by routing to the appropriate tool then
synthesising a natural-language response.

Graph structure:
    Planner ──"predict"──────▶ PredictTool ──┐
             ──"workload"────▶ WorkloadTool ──┼──▶ Responder ──▶ END
             ──"direct"───────────────────────┘

The compiled ``analytics_app`` is ready for future HTTP route integration.
"""

import json
import logging

from langgraph.graph import END, START, StateGraph

from services.api.app.agents.state import AgentState
from services.api.app.clients.ollama_client import ollama_client
from services.api.app.tools.predict_case_duration import predict_case_duration
from services.api.app.tools.workload_management import workload_management

logger = logging.getLogger(__name__)

# ── Planner ────────────────────────────────────────────────────────────────

_ANALYTICS_PLANNER_PROMPT = """\
You are an analytics routing agent for the Sheria judicial platform.

Classify the user's query into exactly one of these intents:
  predict   — request to forecast the duration or delay risk of a specific case
  workload  — request about court workload, caseload statistics, or backlog analysis
  direct    — any other question that can be answered without external tools

When intent is "predict", also include:
  "tool_input": JSON string with keys case_type, court, parties_count, complexity, description

When intent is "workload", also include:
  "tool_input": JSON string with keys court, days

Output JSON ONLY — no prose, no markdown:
{
  "intent": "predict" | "workload" | "direct",
  "tool_input": "<JSON string or empty string>"
}
"""


async def _analytics_planner(state: AgentState) -> dict:
    """Classify the analytics query and prepare tool_input.

    Falls back to ``intent="direct"`` on any error.
    """
    last_msg = state["messages"][-1]
    query: str = (
        last_msg.content if hasattr(last_msg, "content") else last_msg["content"]
    )

    try:
        response = await ollama_client.chat_completion(
            messages=[
                {"role": "system", "content": _ANALYTICS_PLANNER_PROMPT},
                {"role": "user", "content": query},
            ],
            temperature=0.0,
            json_mode=True,
        )
        plan = json.loads(response)
        intent: str = plan.get("intent", "direct")
        tool_input: str = plan.get("tool_input", "")
    except Exception:
        logger.exception("Analytics planner failed, falling back to direct")
        intent = "direct"
        tool_input = ""

    return {
        "current_query": query,
        "action": intent,
        "tool_choice": intent if intent in ("predict", "workload") else "",
        "tool_input": tool_input,
        "plan": [f"analytics intent={intent}"],
    }


# ── Tool nodes ─────────────────────────────────────────────────────────────


async def _predict_tool_node(state: AgentState) -> dict:
    """Call predict_case_duration with state["tool_input"]."""
    result = await predict_case_duration(state.get("tool_input", "{}"))
    return {"messages": [{"role": "user", "content": f"Tool Output: {result}"}]}


async def _workload_tool_node(state: AgentState) -> dict:
    """Call workload_management with state["tool_input"]."""
    result = await workload_management(state.get("tool_input", "{}"))
    return {"messages": [{"role": "user", "content": f"Tool Output: {result}"}]}


# ── Responder ──────────────────────────────────────────────────────────────

_ANALYTICS_RESPONDER_PROMPT = """\
You are Sheria Analytics, an AI assistant for Kenya's judiciary.
You help judges and court staff interpret case duration predictions and workload statistics.

Use the tool output below to answer the user's question in plain, concise language.
If the tool returned an error, explain the issue clearly and suggest next steps.
Do NOT fabricate statistics or case outcomes.
"""


async def _analytics_responder(state: AgentState) -> dict:
    """Synthesise the final natural-language response from tool output."""
    query = state.get("current_query", "")

    # Collect the most recent tool output from messages
    messages = state.get("messages", [])
    tool_outputs = [
        m["content"] for m in messages if m.get("role") == "user" and m["content"].startswith("Tool Output:")
    ]
    tool_context = tool_outputs[-1] if tool_outputs else "No tool output available."

    prompt = (
        f"{_ANALYTICS_RESPONDER_PROMPT}\n\n"
        f"User question: {query}\n\n"
        f"{tool_context}"
    )

    try:
        answer = await ollama_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=512,
        )
    except Exception as exc:
        logger.error("Analytics responder failed: %s", exc)
        answer = "I encountered an error generating the analytics response. Please try again."

    return {"messages": [{"role": "assistant", "content": answer}]}


# ── Routing ────────────────────────────────────────────────────────────────


def _route_after_analytics_planner(state: AgentState) -> str:
    """Route to predict_tool, workload_tool, or responder based on intent."""
    intent = state.get("action", "direct")
    if intent == "predict":
        return "predict_tool"
    if intent == "workload":
        return "workload_tool"
    return "responder"


# ── Graph construction ─────────────────────────────────────────────────────

_analytics_workflow = StateGraph(AgentState)

_analytics_workflow.add_node("planner", _analytics_planner)
_analytics_workflow.add_node("predict_tool", _predict_tool_node)
_analytics_workflow.add_node("workload_tool", _workload_tool_node)
_analytics_workflow.add_node("responder", _analytics_responder)

_analytics_workflow.add_edge(START, "planner")

_analytics_workflow.add_conditional_edges(
    "planner",
    _route_after_analytics_planner,
    {
        "predict_tool": "predict_tool",
        "workload_tool": "workload_tool",
        "responder": "responder",
    },
)

_analytics_workflow.add_edge("predict_tool", "responder")
_analytics_workflow.add_edge("workload_tool", "responder")
_analytics_workflow.add_edge("responder", END)

# ── Compiled application ───────────────────────────────────────────────────

analytics_app = _analytics_workflow.compile()
"""Compiled LangGraph analytics runnable. Import for future route integration."""
