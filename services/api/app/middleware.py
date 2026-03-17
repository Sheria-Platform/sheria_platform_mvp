# services/api/app/middleware.py
"""Custom Starlette middleware for the Sheria Platform API.

Each middleware class has a single responsibility and is registered in
``services/api/main.py`` via ``app.add_middleware(...)``.
"""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from libs.observability.metrics import REQUEST_COUNT, REQUEST_LATENCY
from services.api.app.logging import bind_context

logger = logging.getLogger(__name__)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Attaches a trace_id to every request and logs start/end with latency.

    For each incoming request this middleware:
    1. Generates a unique ``trace_id`` (UUID4).
    2. Calls ``bind_context(trace_id=...)`` so the ID appears in every log
       record emitted anywhere in the request's async task.
    3. Logs request start (method, path).
    4. After the handler returns, logs completion with HTTP status and
       ``duration_ms``.
    5. Increments Prometheus ``REQUEST_COUNT`` and ``REQUEST_LATENCY``.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        trace_id = str(uuid.uuid4())
        bind_context(trace_id=trace_id)

        start = time.perf_counter()
        logger.info(
            "Request started",
            extra={"method": request.method, "path": str(request.url.path)},
        )

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        endpoint = str(request.url.path)

        REQUEST_LATENCY.labels(endpoint=endpoint).observe(duration_ms / 1000)
        REQUEST_COUNT.labels(
            method=request.method,
            endpoint=endpoint,
            status=response.status_code,
        ).inc()

        logger.info(
            "Request completed",
            extra={
                "path": endpoint,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )

        return response
