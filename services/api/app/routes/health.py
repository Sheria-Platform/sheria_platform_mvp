# services/api/app/routes/health.py
@router.get("/readiness")
async def readiness(response: Response):
    """
    K8s Readiness Probe.
    Checks connections to critical dependencies (Redis, DB).
    If this fails, K8s stops sending traffic to this pod.
    """
    status_report = {"redis": "down", "neo4j": "down"}
    is_healthy = True

    # 1. Check Redis
    try:
        r = redis_client.get_client()
        if await r.ping():
            status_report["redis"] = "up"
    except Exception:
        is_healthy = False

    # 2. Check Neo4j (Connectivity only)
    try:
        # Driver is singleton, check if initialized
        if neo4j_client._driver:
            status_report["neo4j"] = "up"
        else:
             is_healthy = False
    except Exception:
        is_healthy = False

    if not is_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    
    return status_report