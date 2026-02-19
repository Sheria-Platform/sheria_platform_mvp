# services/api/app/routes/health.py
"""Kubernetes health-check endpoints.

Exposes two probes consumed by Kubernetes (or any orchestrator):

* ``GET /health/liveness``  -- always 200 while the process is alive.
* ``GET /health/readiness`` -- 200 when dependencies are healthy,
  503 otherwise.

The readiness probe checks Redis (ping) and Neo4j (driver
initialised).  If either fails the pod is removed from the load
balancer until it recovers.
"""

import logging

from fastapi import APIRouter, Response, status

from services.api.app.cache.redis import redis_client
from services.api.app.clients.neo4j import neo4j_client

router = APIRouter()
logger = logging.getLogger(__name__)


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
    """Check dependency health and return 200 or 503.

    Kubernetes uses this to decide whether to *send traffic* to the
    pod.  Checks Redis connectivity and Neo4j driver initialisation.

    Args:
        response: FastAPI ``Response`` object used to override the
            HTTP status code to 503 when unhealthy.

    Returns:
        A dict mapping dependency names to ``"up"`` or ``"down"``,
        e.g. ``{"redis": "up", "neo4j": "up"}``.

    Note:
        A 503 response does *not* restart the container -- it only
        removes the pod from the service endpoints.
    """
    status_report: dict[str, str] = {
        "redis": "down",
        "neo4j": "down",
    }
    is_healthy = True

    # -- Redis check -------------------------------------------------------
    try:
        redis = redis_client.get_client()
        if await redis.ping():
            status_report["redis"] = "up"
    except Exception as exc:
        logger.warning("Readiness: Redis check failed: %s", exc)
        is_healthy = False

    # -- Neo4j check (driver presence only -- no round-trip) --------------
    try:
        if neo4j_client._driver:
            status_report["neo4j"] = "up"
        else:
            is_healthy = False
    except Exception as exc:
        logger.warning("Readiness: Neo4j check failed: %s", exc)
        is_healthy = False

    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return status_report
