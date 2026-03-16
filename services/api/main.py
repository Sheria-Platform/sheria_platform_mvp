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
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
from qdrant_client.http.models import Distance, VectorParams
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from libs.observability.metrics import REQUEST_COUNT, REQUEST_LATENCY
from libs.observability.tracing import configure_tracing
from services.api.app.cache.redis import redis_client
from services.api.app.clients.neo4j import neo4j_client
from services.api.app.clients.ollama_client import ollama_client
from services.api.app.clients.qdrant import qdrant_client
from services.api.app.config import settings
from services.api.app.limiter import limiter
from services.api.app.logging import bind_context
from services.api.app.memory.postgres import Base, engine, postgres_memory
from services.api.app.routes import (
    auth,
    chat,
    feedback,
    health,
    history,
    legal_research,
    upload,
    verify,
)

logger = logging.getLogger(__name__)

# Embedding dimension — must match OLLAMA_EMBEDDING_MODEL output (configured via EMBEDDING_DIM env var)
_EMBEDDING_DIM: int = settings.EMBEDDING_DIM


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

        return response


# ── Startup Helpers ────────────────────────────────────────────────────────


async def _ensure_qdrant_collections() -> None:
    """Create required Qdrant collections if they do not already exist.

    ``semantic_cache`` — stores Q&A embedding pairs for semantic deduplication.
    Uses cosine distance at threshold 0.95 (see cache/semantic.py).

    Safe to call on every startup; existing collections are left untouched.
    """
    existing = {
        c.name for c in (await qdrant_client.client.get_collections()).collections
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

    # Validate kenya_law_reports collection dimension if it already exists
    if "kenya_law_reports" in existing:
        info = await qdrant_client.client.get_collection("kenya_law_reports")
        actual_dim = info.config.params.vectors.size
        if actual_dim != _EMBEDDING_DIM:
            logger.error(
                "DIMENSION MISMATCH: kenya_law_reports collection has %d dimensions "
                "but EMBEDDING_DIM=%d. Vector searches will fail silently. "
                "Drop and recreate the collection with the correct dimension.",
                actual_dim,
                _EMBEDDING_DIM,
            )
        else:
            logger.info(
                "kenya_law_reports dimension validated: %d", actual_dim
            )


async def _create_db_tables() -> None:
    """Create all database tables if they do not already exist.

    Runs ``CREATE TABLE IF NOT EXISTS`` for every SQLAlchemy ORM model
    registered under ``Base`` (``chat_history``, ``ingestion_jobs``,
    ``users``, ``feedback``).  Safe to call on every startup — existing
    tables are left untouched.

    Also applies lightweight column-level migrations (``ALTER TABLE … ADD
    COLUMN IF NOT EXISTS``) for columns added after the initial schema was
    created.  Each statement is idempotent so re-running on an up-to-date
    schema is a no-op.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Phase 3 addition: activation token TTL columns
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                "activation_token_expires_at TIMESTAMP WITHOUT TIME ZONE"
            )
        )
        await conn.execute(
            __import__("sqlalchemy").text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                "approved_by VARCHAR"
            )
        )


async def _seed_admin() -> None:
    """Create the default admin account on first boot if none exists.

    Credentials are read from ``ADMIN_*`` environment variables so they
    can be rotated without code changes.  The seed is skipped when any
    admin already exists, making it safe to call on every startup.
    """
    import bcrypt  # use bcrypt directly — passlib 1.7.4 is incompatible with bcrypt>=4

    hashed = bcrypt.hashpw(
        settings.ADMIN_PASSWORD.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")

    created = await postgres_memory.seed_admin(
        username=settings.ADMIN_USERNAME,
        email=settings.ADMIN_EMAIL,
        full_name=settings.ADMIN_FULL_NAME,
        hashed_password=hashed,
    )
    if created:
        logger.info(
            "Default admin account created",
            extra={"username": settings.ADMIN_USERNAME},
        )
    else:
        logger.info("Admin account already exists — skipping seed")


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
    await _seed_admin()
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

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.ALLOWED_ORIGINS.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)

# ── Route Registration ────────────────────────────────────────────────────
app.include_router(chat.router, prefix="/api/v1/chat", tags=["Chat"])
app.include_router(upload.router, prefix="/api/v1/upload", tags=["Upload"])
app.include_router(feedback.router, prefix="/api/v1/feedback", tags=["Feedback"])
app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(history.router, prefix="/api/v1/history", tags=["History"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Auth"])
app.include_router(
    legal_research.router,
    prefix="/api/v1/legal-research",
    tags=["Legal Research"],
)
app.include_router(verify.router, prefix="/api/v1/verify", tags=["Verify"])

# ── Prometheus Metrics Endpoint ───────────────────────────────────────────
# Mounted as a sub-application so prometheus_client handles content
# negotiation (text/plain vs. OpenMetrics) automatically.
# Scraped by Prometheus at GET /metrics
app.mount("/metrics", make_asgi_app())

if __name__ == "__main__":
    import uvicorn

    # Development convenience — production uses the Docker CMD
    uvicorn.run(app, host="0.0.0.0", port=8000)  # noqa: S104
