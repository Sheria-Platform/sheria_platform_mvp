# services/api/app/streaming.py
"""Shared LangGraph streaming helper.

Provides ``iter_agent_events``, an async generator that wraps a LangGraph
``astream`` call with per-node timing, Prometheus metrics, and status NDJSON
events.

Route handlers iterate this generator, yield the pre-built status lines, and
add their own answer/citation extraction logic.
"""

import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import Any

from libs.observability.metrics import NODE_LATENCY
from services.api.app.agents.state import AgentState

logger = logging.getLogger(__name__)


async def iter_agent_events(
    agent_app: Any,
    initial_state: AgentState,
    config: dict,
    session_id: str,
    metric_prefix: str = "",
) -> AsyncGenerator[tuple[str, dict, str], None]:
    """Iterate LangGraph agent events with timing, metrics, and status NDJSON.

    For each node that fires:

    1. Measures per-node wall-clock latency.
    2. Records ``NODE_LATENCY`` Prometheus histogram.
    3. Logs node completion at INFO level.
    4. Yields ``(node_name, node_data, status_json_line)`` so the caller
       can ``yield status_json_line`` directly and inspect ``node_data``
       for answer/citation extraction.

    Args:
        agent_app: Compiled LangGraph runnable (``agent_app`` or
            ``legal_research_app``).
        initial_state: The ``AgentState`` dict to start the graph.
        config: LangGraph run config (``{"configurable": {...}}``).
        session_id: Used to populate the ``"session_id"`` field in status
            NDJSON events.
        metric_prefix: Optional label prefix for ``NODE_LATENCY``
            (e.g. ``"legal_"`` for the legal-research graph).

    Yields:
        3-tuples of ``(node_name, node_data, status_json_line)`` where
        ``status_json_line`` is a ready-to-yield NDJSON string.
    """
    node_start = time.perf_counter()
    async for event in agent_app.astream(initial_state, config):
        node_name = next(iter(event.keys()))
        node_data = event[node_name]

        duration_ms = round((time.perf_counter() - node_start) * 1000, 2)
        NODE_LATENCY.labels(node=f"{metric_prefix}{node_name}").observe(
            duration_ms / 1000
        )
        logger.info(
            "Agent node completed",
            extra={"node": node_name, "duration_ms": duration_ms},
        )

        status_json = (
            json.dumps({"event": "status", "step": node_name, "session_id": session_id})
            + "\n"
        )
        yield node_name, node_data, status_json
        node_start = time.perf_counter()  # reset after yield so HTTP flush time is excluded
