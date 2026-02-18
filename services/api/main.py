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

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

from services.api.app.cache.redis import redis_client
from services.api.app.clients.neo4j import neo4j_client
from services.api.app.clients.ollama_client import ollama_client
from services.api.app.clients.qdrant import qdrant_client
from services.api.app.routes import chat, feedback, health, upload


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage startup and shutdown of all shared service clients.

    Follows the FastAPI recommended lifespan pattern.  Resources
    initialised before ``yield`` are torn down after ``yield``.

    Startup order:
        1. Neo4j driver (synchronous pool open)
        2. Redis connection pool
        3. Qdrant client (health-check on connect)
        4. Ollama HTTP client pool

    Shutdown is performed in reverse order to respect dependencies.

    Args:
        app: The FastAPI application instance (unused but required by
            the lifespan protocol).

    Yields:
        Nothing — control returns to FastAPI while the server runs.
    """
    # ── Startup ──────────────────────────────────────────────────────
    print("Initializing clients...")
    neo4j_client.connect()
    await redis_client.connect()
    await qdrant_client.connect()
    await ollama_client.start()
    print("All clients initialized successfully!")

    yield

    # ── Shutdown ─────────────────────────────────────────────────────
    print("Closing clients...")
    await ollama_client.close()
    await qdrant_client.disconnect()
    await redis_client.close()
    await neo4j_client.close()
    print("All clients closed successfully!")


# ── Application ───────────────────────────────────────────────────────────
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

# ── Route Registration ────────────────────────────────────────────────────
app.include_router(chat.router, prefix="/api/v1/chat", tags=["Chat"])
app.include_router(upload.router, prefix="/api/v1/upload", tags=["Upload"])
app.include_router(
    feedback.router, prefix="/api/v1/feedback", tags=["Feedback"]
)
app.include_router(health.router, prefix="/health", tags=["Health"])

if __name__ == "__main__":
    import uvicorn

    # Development convenience — production uses the Docker CMD
    uvicorn.run(app, host="0.0.0.0", port=8000)
