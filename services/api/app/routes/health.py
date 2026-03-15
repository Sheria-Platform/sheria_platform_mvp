# services/api/app/routes/health.py
"""Kubernetes health-check endpoints.

Exposes two probes consumed by Kubernetes (or any orchestrator):

* ``GET /health/liveness``  -- always 200 while the process is alive.
* ``GET /health/readiness`` -- 200 when all dependencies are healthy,
  503 otherwise.

The readiness probe checks all application services: PostgreSQL, Redis,
Qdrant, Neo4j, Ollama, and MinIO (skipped when MINIO_SERVER_URL is not
configured).  All checks run concurrently with a 5-second timeout each.
"""

import asyncio
import logging

import httpx
from fastapi import APIRouter, Response, status
from sqlalchemy import text

from services.api.app.cache.redis import redis_client
from services.api.app.clients.neo4j import neo4j_client
from services.api.app.clients.ollama_client import ollama_client
from services.api.app.clients.qdrant import qdrant_client
from services.api.app.config import settings
from services.api.app.memory.postgres import engine

router = APIRouter()
logger = logging.getLogger(__name__)

_TIMEOUT = 5.0  # seconds per individual check


# ── Per-service check helpers ─────────────────────────────────────────────────


async def _check_postgres() -> str:
    try:
        async with engine.connect() as conn:
            await asyncio.wait_for(
                conn.execute(text("SELECT 1")), timeout=_TIMEOUT
            )
        return "up"
    except Exception as exc:
        logger.warning("Readiness: PostgreSQL check failed: %s", exc)
        return "down"


async def _check_redis() -> str:
    try:
        r = redis_client.get_client()
        await asyncio.wait_for(r.ping(), timeout=_TIMEOUT)
        return "up"
    except Exception as exc:
        logger.warning("Readiness: Redis check failed: %s", exc)
        return "down"


async def _check_qdrant() -> str:
    try:
        await asyncio.wait_for(
            qdrant_client.client.get_collections(), timeout=_TIMEOUT
        )
        return "up"
    except Exception as exc:
        logger.warning("Readiness: Qdrant check failed: %s", exc)
        return "down"


async def _check_neo4j() -> str:
    try:
        if not neo4j_client._driver:
            return "down"
        await asyncio.wait_for(
            neo4j_client.query("RETURN 1"), timeout=_TIMEOUT
        )
        return "up"
    except Exception as exc:
        logger.warning("Readiness: Neo4j check failed: %s", exc)
        return "down"


async def _check_ollama() -> str:
    try:
        ok = await asyncio.wait_for(
            ollama_client.health_check(), timeout=_TIMEOUT
        )
        return "up" if ok else "down"
    except Exception as exc:
        logger.warning("Readiness: Ollama check failed: %s", exc)
        return "down"


async def _check_minio() -> str:
    url = settings.MINIO_SERVER_URL
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(f"{url.rstrip('/')}/minio/health/live")
            return "up" if resp.status_code == 200 else "down"
    except Exception as exc:
        logger.warning("Readiness: MinIO check failed: %s", exc)
        return "down"


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/liveness", summary="Liveness probe")
async def liveness() -> dict[str, str]:
    """Return 200 OK while the server process is running.

    Kubernetes uses this to decide whether to *restart* the container.
    It should never block or perform I/O.

    Returns:
        ``{"status": "ok"}``
    """
    return {"status": "ok"}


@router.get("/readiness", summary="Readiness probe")
async def readiness(response: Response) -> dict[str, str]:
    """Check all dependency health and return 200 or 503.

    Runs checks for PostgreSQL, Redis, Qdrant, Neo4j, Ollama, and MinIO
    concurrently.  MinIO is included only when ``MINIO_SERVER_URL`` is
    configured.

    Kubernetes uses this to decide whether to *send traffic* to the pod.

    Args:
        response: FastAPI ``Response`` object used to set 503 when any
            service is down.

    Returns:
        A dict mapping each service name to ``"up"`` or ``"down"``.

    Note:
        A 503 response does *not* restart the container — it only removes
        the pod from the service endpoints until all checks pass.
    """
    checks = {
        "postgres": _check_postgres(),
        "redis": _check_redis(),
        "qdrant": _check_qdrant(),
        "neo4j": _check_neo4j(),
        "ollama": _check_ollama(),
    }
    if settings.MINIO_SERVER_URL:
        checks["minio"] = _check_minio()

    results = await asyncio.gather(*checks.values())
    status_report: dict[str, str] = dict(zip(checks.keys(), results))

    if any(v == "down" for v in status_report.values()):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return status_report
