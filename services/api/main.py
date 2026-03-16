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
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import make_asgi_app
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from libs.observability.tracing import configure_tracing
from services.api.app.cache.redis import redis_client
from services.api.app.clients.neo4j import neo4j_client
from services.api.app.clients.ollama_client import ollama_client
from services.api.app.clients.qdrant import qdrant_client
from services.api.app.config import settings
from services.api.app.limiter import limiter
from services.api.app.middleware import RequestLoggingMiddleware
from services.api.app.startup import create_db_tables, ensure_qdrant_collections, seed_admin
from services.api.app.routes import (
    auth,
    chat,
    feedback,
    health,
    history,
    legal_research,
    predict,
    upload,
    verify,
)

logger = logging.getLogger(__name__)


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
    await create_db_tables()
    await seed_admin()
    neo4j_client.connect()
    await redis_client.connect()
    await qdrant_client.connect()
    try:
        await ensure_qdrant_collections()
    except Exception as exc:
        logger.warning(
            "Qdrant collection setup skipped — Qdrant unreachable at startup. "
            "Collections will be created on the next successful connection. error=%s",
            exc,
        )
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
app.include_router(predict.router, prefix="/api/v1/predict", tags=["Predict"])

# ── Prometheus Metrics Endpoint ───────────────────────────────────────────
# Mounted as a sub-application so prometheus_client handles content
# negotiation (text/plain vs. OpenMetrics) automatically.
# Scraped by Prometheus at GET /metrics
app.mount("/metrics", make_asgi_app())

if __name__ == "__main__":
    import uvicorn

    # Development convenience — production uses the Docker CMD
    uvicorn.run(app, host="0.0.0.0", port=8000)  # noqa: S104
