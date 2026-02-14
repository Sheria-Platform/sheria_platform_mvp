# services/api/main.py
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from services.api import custom_openapi
from services.api.app.cache.redis import redis_client
from services.api.app.clients.neo4j import neo4j_client
from services.api.app.clients.qdrant import qdrant_client
from services.api.app.clients.ray_embed import embed_client
from services.api.app.clients.ray_llm import llm_client
from services.api.app.config import settings
from services.api.app.logging import setup_logging, LOGGING
from services.api.app.routes import chat, health, upload

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
    logger.info("Initializing clients...")
    neo4j_client.connect()
    await redis_client.connect()
    await qdrant_client.connect()

    # Only call start/close if methods exist (Ray clients might not need them)
    if hasattr(llm_client, "start") and callable(getattr(llm_client, "start")):
        await llm_client.start()
    if hasattr(embed_client, "start") and callable(getattr(embed_client, "start")):
        await embed_client.start()

    logger.info("All clients initialized successfully!")

    yield

    # 2. Shutdown
    logger.info("Closing clients...")
    await neo4j_client.close()
    await redis_client.close()
    await qdrant_client.disconnect()

    if hasattr(llm_client, "close") and callable(getattr(llm_client, "close")):
        await llm_client.close()
    if hasattr(embed_client, "close") and callable(getattr(embed_client, "close")):
        await embed_client.close()

    logger.info("All clients closed successfully!")

is_secure = os.environ.get('environment') == 'secure'


app = FastAPI(title="Enterprise RAG Platform", version="1.0.0", lifespan=lifespan)

# Include Routes
app.include_router(chat.router, prefix="/api/v1/chat", tags=["Chat"])
app.include_router(upload.router, prefix="/api/v1/upload", tags=["Upload"])
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
