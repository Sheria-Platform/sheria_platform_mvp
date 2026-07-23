# services/api/app/routes/upload.py
"""S3 presigned-URL generation endpoint.

Allows authenticated clients to upload court documents directly to S3
without proxying the file through the API server.  The client receives
a time-limited presigned PUT URL and uploads the file client-side.

Typical flow:
    1. Client calls ``POST /api/v1/upload/generate-presigned-url``.
    2. Server returns ``upload_url``, ``file_id``, ``s3_key``.
    3. Client PUTs the file binary to ``upload_url``.
    4. Client notifies the ingestion pipeline with ``s3_key``.
"""

import asyncio
import concurrent.futures
import os
import threading
import time
import uuid
from datetime import datetime
from typing import Any

import boto3
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from services.api.app.auth.permissions import require_role
from services.api.app.auth.jwt import get_current_user
from services.api.app.config import settings
from services.api.app.memory.ingestion_repository import ingestion_repository

router = APIRouter()

# Bounded thread pool — prevents unbounded parallelism under concurrent uploads
_MAX_CONCURRENT_JOBS = int(os.getenv("MAX_CONCURRENT_INGEST_JOBS", "4"))
_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=_MAX_CONCURRENT_JOBS,
    thread_name_prefix="ingest",
)

# The main asyncio event loop — captured once at startup by set_main_loop().
# Worker threads must schedule DB coroutines onto THIS loop (not a new one)
# because SQLAlchemy's asyncpg connection pool is bound to it.
_main_loop: asyncio.AbstractEventLoop | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    """Store the main event loop so worker threads can use run_coroutine_threadsafe."""
    global _main_loop
    _main_loop = loop

# boto3 presigning is CPU-bound and very fast (~1 ms); a sync client
# is acceptable here -- no I/O occurs until the client uploads.
# When MINIO_SERVER_URL is set (local dev), point boto3 at MinIO.
if settings.MINIO_SERVER_URL:
    _s3 = boto3.client(
        "s3",
        endpoint_url=settings.MINIO_SERVER_URL,
        aws_access_key_id=settings.MINIO_ROOT_USER,
        aws_secret_access_key=settings.MINIO_ROOT_PASSWORD,
        region_name="us-east-1",
    )
else:
    _s3 = boto3.client("s3", region_name=settings.AWS_REGION)

# Presigned URL validity window in seconds (1 hour)
_PRESIGNED_URL_TTL = 3600


class PresignedURLRequest(BaseModel):
    """Request body for presigned URL generation.

    Attributes:
        filename: Original filename including extension
            (e.g. ``"judgment_2023.pdf"``).
        content_type: MIME type of the file being uploaded
            (e.g. ``"application/pdf"``).
    """

    filename: str
    content_type: str


class PresignedURLResponse(BaseModel):
    """Response containing the presigned URL and storage metadata.

    Attributes:
        upload_url: Temporary S3 presigned PUT URL.  Valid for
            ``_PRESIGNED_URL_TTL`` seconds.
        file_id: UUID assigned to this upload for downstream tracking.
        s3_key: Full S3 object key where the file will be stored.
    """

    upload_url: str
    file_id: str
    s3_key: str


async def recover_stale_jobs() -> None:
    """Mark any jobs still in 'pending'/'running' state in the DB as 'failed'.

    Called at application startup to clean up jobs that were interrupted by a
    server restart.  Without this, the UI would show those jobs stuck forever.
    """
    try:
        from services.api.app.memory.models import AsyncSessionLocal, IngestionJob
        from sqlalchemy import update

        async with AsyncSessionLocal() as session:
            await session.execute(
                update(IngestionJob)
                .where(IngestionJob.status.in_(["pending", "running"]))
                .values(
                    status="failed",
                    error="Server restarted while job was in progress.",
                    completed_at=datetime.utcnow(),
                )
            )
            await session.commit()
    except Exception as exc:
        # Non-fatal — log and continue startup
        import logging
        logging.getLogger(__name__).warning("Could not recover stale jobs: %s", exc)


def shutdown_executor() -> None:
    """Gracefully drain the ingest thread pool.  Call from app lifespan shutdown."""
    _executor.shutdown(wait=False, cancel_futures=False)


@router.post(
    "/generate-presigned-url",
    response_model=PresignedURLResponse,
    summary="Generate S3 presigned upload URL",
)
async def generate_upload_url(
    req: PresignedURLRequest,
    user: dict = Depends(get_current_user),
) -> PresignedURLResponse:
    """Generate a time-limited S3 presigned URL for direct file upload.

    The presigned URL allows the client to PUT the file binary directly
    to S3, bypassing the API server entirely for large files
    (PDFs, court recordings, etc.).

    Args:
        req: Upload request containing ``filename`` and
            ``content_type``.
        user: Authenticated user dict from ``get_current_user``.

    Returns:
        A ``PresignedURLResponse`` with the upload URL, assigned
        ``file_id``, and ``s3_key``.

    Raises:
        HTTPException(500): If boto3 fails to generate the presigned
            URL (e.g. invalid bucket or IAM permissions issue).

    Example:
        Request::

            POST /api/v1/upload/generate-presigned-url
            {
                "filename": "judgment_2023.pdf",
                "content_type": "application/pdf"
            }

        Response::

            {
                "upload_url": "https://s3.amazonaws.com/...",
                "file_id": "550e8400-e29b-41d4-a716-446655440000",
                "s3_key": "uploads/judge-001/550e8400....pdf"
            }
    """
    if not settings.S3_BUCKET_NAME:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="S3_BUCKET_NAME is not configured. Set it in .env.",
        )

    file_id = str(uuid.uuid4())
    extension = req.filename.rsplit(".", 1)[-1] if "." in req.filename else "bin"
    s3_key = f"uploads/{user['id']}/{file_id}.{extension}"

    try:
        url: str = _s3.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": settings.S3_BUCKET_NAME,
                "Key": s3_key,
                "ContentType": req.content_type,
            },
            ExpiresIn=_PRESIGNED_URL_TTL,
        )
        return PresignedURLResponse(upload_url=url, file_id=file_id, s3_key=s3_key)

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# In-memory job store -- live status cache; persisted to PostgreSQL for durability
# ---------------------------------------------------------------------------
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()


class IngestRequest(BaseModel):
    s3_key: str
    file_id: str
    filename: str | None = None  # original filename for display


class JobStatus(BaseModel):
    job_id: str
    status: str  # pending | running | done | failed
    filename: str = ""
    s3_key: str = ""
    started_at: float | None = None  # unix timestamp
    completed_at: float | None = None
    duration_s: float | None = None
    stats: dict = {}
    error: str = ""


def _run_ingest(job_id: str, bucket: str, s3_key: str, user_id: str) -> None:
    # DB coroutines must run on the MAIN event loop where SQLAlchemy's asyncpg
    # connection pool was created.  Scheduling onto a new loop causes:
    #   "Future attached to a different loop"
    # run_coroutine_threadsafe() is the correct bridge from a worker thread.
    if _main_loop is None:
        raise RuntimeError("Main event loop not captured; call set_main_loop() at startup.")

    def _db(coro):
        """Schedule a coroutine on the main loop and block until it completes."""
        return asyncio.run_coroutine_threadsafe(coro, _main_loop).result(timeout=30)

    try:
        with _jobs_lock:
            _jobs[job_id]["status"] = "running"
            _jobs[job_id]["started_at"] = time.time()
        _db(ingestion_repository.update_ingestion_job(job_id, status="running"))

        from pipelines.ingestion.main import main as ingest_main  # lazy import

        exit_code, stats = ingest_main(bucket_name=bucket, prefix=s3_key)
        completed = time.time()
        final_status = "done" if exit_code == 0 else "failed"
        with _jobs_lock:
            _jobs[job_id]["status"] = final_status
            _jobs[job_id]["stats"] = stats
            _jobs[job_id]["completed_at"] = completed
            _jobs[job_id]["duration_s"] = round(
                completed - (_jobs[job_id].get("started_at") or completed), 1
            )
        _db(
            ingestion_repository.update_ingestion_job(
                job_id,
                status=final_status,
                completed_at=datetime.utcfromtimestamp(completed),
                duration_s=_jobs[job_id]["duration_s"],
                stats=stats,
            )
        )
    except Exception as exc:
        completed = time.time()
        duration = round(completed - (_jobs[job_id].get("started_at") or completed), 1)
        with _jobs_lock:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = str(exc)
            _jobs[job_id]["completed_at"] = completed
            _jobs[job_id]["duration_s"] = duration
        _db(
            ingestion_repository.update_ingestion_job(
                job_id,
                status="failed",
                completed_at=datetime.utcfromtimestamp(completed),
                duration_s=duration,
                error=str(exc),
            )
        )


@router.post(
    "/ingest",
    response_model=JobStatus,
    summary="Trigger ingestion for an uploaded file",
)
async def trigger_ingest(
    req: IngestRequest,
    user: dict = Depends(require_role("judge", "magistrate", "registrar", "clerk")),
) -> JobStatus:
    """Start the ingestion pipeline for a file that was just uploaded to MinIO."""
    if not settings.S3_BUCKET_NAME:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="S3_BUCKET_NAME is not configured.",
        )
    job_id = str(uuid.uuid4())
    started_ts = time.time()
    filename = req.filename or req.s3_key.rsplit("/", 1)[-1]
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "pending",
            "filename": filename,
            "s3_key": req.s3_key,
            "user_id": user["id"],
            "started_at": started_ts,
            "completed_at": None,
            "duration_s": None,
            "stats": {},
            "error": "",
        }

    await ingestion_repository.create_ingestion_job(
        job_id=job_id,
        user_id=user["id"],
        filename=filename,
        s3_key=req.s3_key,
        started_at=datetime.utcfromtimestamp(started_ts),
    )

    _executor.submit(_run_ingest, job_id, settings.S3_BUCKET_NAME, req.s3_key, user["id"])
    return JobStatus(
        job_id=job_id,
        status="pending",
        **{k: _jobs[job_id][k] for k in ("filename", "s3_key", "started_at")},
    )


@router.get("/jobs", response_model=list[JobStatus], summary="List all ingestion jobs")
async def list_jobs(
    user: dict = Depends(get_current_user),
) -> list[JobStatus]:
    rows = await ingestion_repository.get_all_ingestion_jobs(user["id"])
    return [JobStatus(**r) for r in rows]


@router.get(
    "/jobs/{job_id}", response_model=JobStatus, summary="Poll ingestion job status"
)
async def get_job_status(
    job_id: str,
    user: dict = Depends(get_current_user),
) -> JobStatus:
    # In-memory gives live status for active jobs
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job and job.get("user_id") == user["id"]:
        return JobStatus(
            job_id=job_id,
            **{k: v for k, v in job.items() if k != "user_id"},
        )
    # Fall back to DB for completed / pre-restart jobs
    row = await ingestion_repository.get_ingestion_job(job_id, user["id"])
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Job not found"
        )
    return JobStatus(**row)
