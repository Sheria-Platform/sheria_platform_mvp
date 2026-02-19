# services/api/main.py
import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi import FastAPI
from qdrant_client.http.models import Distance, VectorParams
from sqlalchemy import text

from services.api import custom_openapi
from services.api.app.cache.redis import redis_client
from services.api.app.clients.neo4j import neo4j_client
from services.api.app.clients.ollama_client import ollama_client
from services.api.app.clients.qdrant import qdrant_client
from services.api.app.clients.ray_embed import embed_client
from services.api.app.clients.ray_llm import llm_client
from services.api.app.config import settings
from services.api.app.logging import setup_logging, LOGGING
from services.api.app.routes import chat, health, upload
from services.api.app.memory.postgres import Base, engine
from services.api.app.routes import chat, feedback, health, upload

# Dimension produced by nomic-embed-text (must match OLLAMA_EMBEDDING_MODEL)
_EMBEDDING_DIM = 2560


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
        print("Created Qdrant collection: semantic_cache")


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

# FastAPI Application
setup_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Centralized Resource Management.
    Initialize all connection pools here.
    """
    # 1. Startup
    print("Initializing clients...")
    neo4j_client.connect()
    await redis_client.connect()
    await qdrant_client.connect()
    await _ensure_qdrant_collections()
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

# Include Routes
app.include_router(chat.router, prefix="/api/v1/chat", tags=["Chat"])
app.include_router(upload.router, prefix="/api/v1/upload", tags=["Upload"])
app.include_router(
    feedback.router, prefix="/api/v1/feedback", tags=["Feedback"]
)
app.include_router(health.router, prefix="/health", tags=["Health"])

if is_secure:
    @app.middleware("http")
    async def set_secure_scheme(request: Request, call_next):
        request.scope["scheme"] = "https"

        response = await call_next(request)

        return response

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=settings.cors_origins,
    allow_methods=[
        "GET",
        "POST",
        "PUT",
        "DELETE",
        "OPTIONS",
        "HEAD",
        "PATCH"
    ],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "If-Match",
        "If-None-Match",
        "If-Modified-Since",
        "If-Unmodified-Since",
        "X-Requested-With",
        "X-CSRF-Token",
        "X-Forwarded-For",
        "X-Forwarded-Proto",
        "X-Forwarded-Host",
        "X-Real-IP",
        "CF-RAY",
        "CF-Visitor",
        "Client-IP",
        "X-Client-IP",
        "X-Requested-With",
        "CF-Connecting-IP",
        "CF-IPCountry",
        "Upgrade",
        "Connection"
    ],
    expose_headers=[
        "Content-Disposition",
        "X-Conversation-Id"
    ]
)

app.openapi_schema = custom_openapi(app)

if __name__ == "__main__":
    import uvicorn

    # In production, this is run via Gunicorn/Uvicorn in Docker
    uvicorn.run(app,
                host="0.0.0.0",
                port=8000,
                reload=True,
                reload_includes=["*.py", '.env'],
                log_level="info",
                log_config=LOGGING)
