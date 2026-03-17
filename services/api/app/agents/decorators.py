# services/api/app/agents/decorators.py
"""Agent node utilities.

Provides ``node_timer``, a lightweight async context manager that logs
start/end events and wall-clock duration for a LangGraph node without
requiring callers to manage ``time.perf_counter()`` manually.
"""

import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager


@asynccontextmanager
async def node_timer(name: str, logger: logging.Logger) -> AsyncGenerator[None, None]:
    """Async context manager that logs node start/end and duration.

    Usage::

        async with node_timer("responder", logger):
            result = await some_llm_call(...)

    Args:
        name: Node name used in log records (``extra={"node": name}``).
        logger: Logger instance to write records to.

    Yields:
        Nothing — control passes to the ``async with`` body.
    """
    logger.info("%s node started", name, extra={"node": name})
    start = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        logger.info(
            "%s node completed",
            name,
            extra={"node": name, "duration_ms": duration_ms},
        )
