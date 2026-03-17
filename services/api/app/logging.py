# services/api/app/logging.py
import contextvars
import json
import logging
import sys
from datetime import datetime, timezone

# ── Request Context ────────────────────────────────────────────────────────
# Stores per-request fields so every log record emitted during a request is
# automatically decorated without callers needing to pass them as extra=.
_request_ctx: contextvars.ContextVar[dict | None] = contextvars.ContextVar(
    "request_context", default=None
)


def bind_context(**kwargs: object) -> None:
    """Attach key-value pairs to the current async context.

    Call this once per request (in middleware or the route handler) to
    inject identifiers — trace_id, session_id, user_id — into every
    subsequent log record within the same async task without having to
    thread them through every function call.

    Example::

        bind_context(trace_id="abc123", session_id="sess-1", user_id="u-42")
        logger.info("Processing request")  # → {"trace_id": "abc123", ...}
    """
    current = (_request_ctx.get() or {}).copy()
    current.update(kwargs)
    _request_ctx.set(current)


# ── JSON Formatter ─────────────────────────────────────────────────────────
class JSONFormatter(logging.Formatter):
    """Formats every log record as a single-line JSON object.

    Automatically merges the current request context (trace_id, session_id,
    user_id, node) so log records are correlated without explicit extra=.
    Per-record extras take precedence over context values (most-specific wins).
    """

    # Fields we promote from LogRecord attributes or context into the JSON body
    _PROMOTED = ("trace_id", "session_id", "user_id", "node", "duration_ms")

    def format(self, record: logging.LogRecord) -> str:
        ctx = _request_ctx.get() or {}

        log_record: dict = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }

        # Merge request context first (lower precedence)
        log_record.update(ctx)

        # Per-record extras override context (most-specific wins)
        for field in self._PROMOTED:
            if hasattr(record, field):
                log_record[field] = getattr(record, field)

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record)


# ── Setup ──────────────────────────────────────────────────────────────────
def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger to emit JSON to stdout."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove default handlers to avoid duplicate logs
    if root_logger.handlers:
        root_logger.handlers = []

    root_logger.addHandler(handler)

    # Silence noisy third-party loggers
    logging.getLogger("uvicorn.access").disabled = True
    logging.getLogger("httpx").setLevel(logging.WARNING)


# Initialize on import
setup_logging()
