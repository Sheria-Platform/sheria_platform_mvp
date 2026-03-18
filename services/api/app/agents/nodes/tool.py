# services/api/app/agents/nodes/tool.py
"""Agent tool node — dispatches tool calls via a registry.

The registry pattern (OCP) means new tools can be added by appending an entry
to ``_TOOL_REGISTRY`` without modifying the dispatch logic in ``tool_node``.

To add a new tool:
    1. Import the function at the top of this module.
    2. Add an entry: ``"my_tool": my_tool_fn`` in ``_TOOL_REGISTRY``.
    Both sync and async callables are supported.
"""

import asyncio
import logging
from collections.abc import Callable

from services.api.app.agents.state import AgentState
from services.api.app.tools.calculator import calculate
from services.api.app.tools.graph_search import search_graph_tool
from services.api.app.tools.predict_case_duration import predict_case_duration
from services.api.app.tools.verify_document import verify_document
from services.api.app.tools.web_search import search_kenya_law_web
from services.api.app.tools.workload_management import workload_management

logger = logging.getLogger(__name__)

# Registry maps tool_name → callable (sync or async) that accepts tool_input str.
_TOOL_REGISTRY: dict[str, Callable] = {
    "calculator": calculate,
    "graph_search": search_graph_tool,
    "predict_case_duration": predict_case_duration,
    "verify_document": verify_document,
    "web_search": search_kenya_law_web,
    "workload_management": workload_management,
}


async def tool_node(state: AgentState) -> dict:
    """Dispatch the tool specified in ``state["tool_choice"]``.

    Looks up the tool in ``_TOOL_REGISTRY`` and calls it with
    ``state["tool_input"]``.  Supports both sync and async callables.
    Returns an error message for unknown tools rather than raising,
    keeping the graph running.

    Args:
        state: Agent state containing ``"plan"``, ``"tool_choice"``,
            and ``"tool_input"`` fields.

    Returns:
        Partial state dict with ``"messages"`` containing the tool result.
    """
    plan_data = state.get("plan", [])
    if not plan_data:
        return {"messages": [{"role": "system", "content": "No tool selected."}]}

    tool_name = state.get("tool_choice", "")
    tool_input = state.get("tool_input", "")

    tool_fn = _TOOL_REGISTRY.get(tool_name)
    if tool_fn is None:
        result = f"Unknown tool: {tool_name!r}. Available: {list(_TOOL_REGISTRY)}"
        logger.warning("Unknown tool requested: %s", tool_name)
    else:
        logger.info("Executing tool %s: %s", tool_name, tool_input)
        raw = tool_fn(tool_input)
        result = await raw if asyncio.iscoroutine(raw) else raw

    return {"messages": [{"role": "system", "content": f"Tool result: {result}"}]}
