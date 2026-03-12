# services/api/main.py
"""Sheria Platform — FastAPI application entry point.

Initialises the FastAPI application, registers all route prefixes, and
manages the lifecycle of every shared client through the async ``lifespan``
context manager (startup → yield → shutdown pattern).

All database and AI-service clients are created once at startup and
closed gracefully at shutdown, preventing connection leaks.

Example:
    Run locally::

        uvicorn services.api.main:app --reload --host 0.0.0.0 --port 8000

    Or via Docker Compose::

        docker compose up sheria-api
"""

import logging
import time
import uuid
from contextlib import asynccontextmanager
import json as _agent_json  # agent log
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
from qdrant_client.http.models import Distance, VectorParams
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from libs.observability.metrics import REQUEST_COUNT, REQUEST_LATENCY
from libs.observability.tracing import configure_tracing
from services.api.app.cache.redis import redis_client
from services.api.app.clients.neo4j import neo4j_client
from services.api.app.clients.ollama_client import ollama_client
from services.api.app.clients.qdrant import qdrant_client
from services.api.app.logging import bind_context
from services.api.app.memory.postgres import Base, engine
from services.api.app.routes import chat, feedback, health, upload

logger = logging.getLogger(__name__)

# Dimension produced by nomic-embed-text (must match OLLAMA_EMBEDDING_MODEL)
_EMBEDDING_DIM = 2560


# ── Request Logging Middleware ─────────────────────────────────────────────

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

        # #region agent log
        try:
            _agent_log = {
                "sessionId": "798f81",
                "runId": "pre-fix",
                "hypothesisId": "H1",
                "location": "services/api/main.py:RequestLoggingMiddleware.dispatch",
                "message": "request completed",
                "data": {
                    "method": request.method,
                    "path": endpoint,
                    "status": response.status_code,
                    "origin": request.headers.get("origin"),
                },
                "timestamp": int(time.time() * 1000),
            }
            _agent_log_path = "/Users/danielmalungu/Documents/sheria_platform_mvp/.cursor/debug-798f81.log"
            with open(_agent_log_path, "a", encoding="utf-8") as _agent_f:
                _agent_f.write(_agent_json.dumps(_agent_log) + "\n")
        except Exception:
            # Intentionally swallow all errors from debug logging.
            pass
        # #endregion
        return response


# ── Startup Helpers ────────────────────────────────────────────────────────

async def _ensure_qdrant_collections() -> None:
    """Create required Qdrant collections if they do not already exist.

    ``semantic_cache`` — stores Q&A embedding pairs for semantic deduplication.
    Uses cosine distance at threshold 0.95 (see cache/semantic.py).

    Safe to call on every startup; existing collections are left untouched.
    """
    existing = {
        c.name
        for c in (await qdrant_client.client.get_collections()).collections
    }

    if "semantic_cache" not in existing:
        await qdrant_client.client.create_collection(
            collection_name="semantic_cache",
            vectors_config=VectorParams(
                size=_EMBEDDING_DIM,
                distance=Distance.COSINE,
            ),
        )
        logger.info("Created Qdrant collection: semantic_cache")


async def _create_db_tables() -> None:
    """Create all database tables if they do not already exist.

    Runs ``CREATE TABLE IF NOT EXISTS`` for every SQLAlchemy ORM model
    (``chat_history``) and the raw-SQL ``feedback`` table.  Safe to call
    on every startup — existing tables are left untouched.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS feedback (
                id         SERIAL PRIMARY KEY,
                session_id VARCHAR      NOT NULL,
                user_id    VARCHAR      NOT NULL,
                message_id INTEGER      NOT NULL,
                score      INTEGER      NOT NULL,
                comment    TEXT,
                created_at TIMESTAMP    DEFAULT NOW()
            )
        """))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup and shutdown of all shared service clients.

    Follows the FastAPI recommended lifespan pattern.  Resources
    initialised before ``yield`` are torn down after ``yield``.

    Startup order:
        1. Database tables (created if missing)
        2. Neo4j driver (synchronous pool open)
        3. Redis connection pool
        4. Qdrant client (health-check on connect)
        5. Qdrant collections (created if missing)
        6. Ollama HTTP client pool

    Shutdown is performed in reverse order to respect dependencies.

    Args:
        app: The FastAPI application instance (unused but required by
            the lifespan protocol).

    Yields:
        Nothing — control returns to FastAPI while the server runs.
    """
    # ── Startup ──────────────────────────────────────────────────────
    logger.info("Initializing clients...")
    await _create_db_tables()
    neo4j_client.connect()
    await redis_client.connect()
    await qdrant_client.connect()
    await _ensure_qdrant_collections()
    await ollama_client.start()
    logger.info("All clients initialized successfully")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    logger.info("Closing clients...")
    await ollama_client.close()
    await qdrant_client.disconnect()
    await redis_client.close()
    await neo4j_client.close()
    logger.info("All clients closed successfully")


# ── Application ───────────────────────────────────────────────────────────
configure_tracing("sheria-api")

app = FastAPI(
    title="Sheria Platform API",
    version="1.0.0",
    description=(
        "AI-powered judicial intelligence for Kenya's court system. "
        "Provides agentic legal research, document verification, and "
        "predictive analytics via a streaming RAG pipeline."
    ),
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)

# ── Route Registration ────────────────────────────────────────────────────
@app.get("/api/v1/health")
async def api_v1_health() -> dict[str, str]:
    # Simple compatibility alias for legacy health checks.
    return {"status": "ok"}

app.include_router(chat.router, prefix="/api/v1/chat", tags=["Chat"])
app.include_router(upload.router, prefix="/api/v1/upload", tags=["Upload"])
app.include_router(
    feedback.router, prefix="/api/v1/feedback", tags=["Feedback"]
)
app.include_router(health.router, prefix="/health", tags=["Health"])

# ── Prometheus Metrics Endpoint ───────────────────────────────────────────
# Mounted as a sub-application so prometheus_client handles content
# negotiation (text/plain vs. OpenMetrics) automatically.
# Scraped by Prometheus at GET /metrics
app.mount("/metrics", make_asgi_app())

if __name__ == "__main__":
    import uvicorn

    # Development convenience — production uses the Docker CMD
    uvicorn.run(app, host="0.0.0.0", port=8000)
