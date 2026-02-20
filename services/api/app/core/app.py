import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi import Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from qdrant_client.http.models import Distance, VectorParams

from services.api.app.cache.redis import redis_client
from services.api.app.clients.neo4j import neo4j_client
from services.api.app.clients.ollama_client import ollama_client
from services.api.app.clients.qdrant import qdrant_client
from services.api.app.core.config import settings
from services.api.app.routes import rag, feedback, health, upload
from services.api.app.tools.exceptions import register_validation_handler

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


def create_app() -> FastAPI:
    is_secure = os.getenv("ENVIRONMENT", '').lower() == "secure"

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

    app.include_router(rag.conversations_router, prefix="/api/v1", tags=["Chat"])
    app.include_router(upload.router, prefix="/api/v1/upload", tags=["Upload"])
    app.include_router(
        feedback.router, prefix="/api/v1/feedback", tags=["Feedback"]
    )
    app.include_router(health.router, prefix="/health", tags=["Health"])

    register_validation_handler(app=app)

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

    return app


def custom_openapi(_app):
    """
    Generate a custom OpenAPI schema with JWT Bearer authentication configuration.

    This function creates or retrieves a cached OpenAPI schema for the Sheria Platform API.
    If the schema already exists, it returns the cached version. Otherwise, it generates
    a new schema with custom security configurations including JWT Bearer authentication.

    Args:
        _app (FastAPI): The FastAPI application instance for which to generate the OpenAPI
                      schema. The app must have a routes attribute containing all registered
                      API routes.

    Returns:
        dict: The OpenAPI schema dictionary containing API documentation, security schemes,
             and all route definitions. The schema includes BearerAuth security configuration
             with JWT format for authentication.
    """
    if _app.openapi_schema:
        return _app.openapi_schema

    openapi_schema = get_openapi(
        title="Sheria Platform API",
        description="API for managing Sheria Platform",
        contact={
            "name": "Sheria Platform Team"
        },
        version="1.0.0",
        routes=_app.routes,
    )
    openapi_schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "Bearer",
            "bearerFormat": "JWT"
        }
    }
    openapi_schema["security"] = [{"BearerAuth": []}]
    _app.openapi_schema = openapi_schema

    return _app.openapi_schema
