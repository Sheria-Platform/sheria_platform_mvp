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

import threading
import uuid
from typing import Any, Dict

import boto3
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from services.api.app.auth.jwt import get_current_user
from services.api.app.config import settings

router = APIRouter()

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
    extension = (
        req.filename.rsplit(".", 1)[-1] if "." in req.filename else "bin"
    )
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
        return PresignedURLResponse(
            upload_url=url, file_id=file_id, s3_key=s3_key
        )

    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# In-memory job store (MVP — restart clears jobs)
# ---------------------------------------------------------------------------
_jobs: Dict[str, Dict[str, Any]] = {}
_jobs_lock = threading.Lock()


class IngestRequest(BaseModel):
    s3_key: str
    file_id: str


class JobStatus(BaseModel):
    job_id: str
    status: str  # pending | running | done | failed
    stats: dict = {}
    error: str = ""


def _run_ingest(job_id: str, bucket: str, s3_key: str) -> None:
    with _jobs_lock:
        _jobs[job_id]["status"] = "running"
    try:
        from pipelines.ingestion.main import main as ingest_main  # lazy import
        exit_code, stats = ingest_main(bucket_name=bucket, prefix=s3_key)
        with _jobs_lock:
            _jobs[job_id]["status"] = "done" if exit_code == 0 else "failed"
            _jobs[job_id]["stats"] = stats
    except Exception as exc:
        with _jobs_lock:
            _jobs[job_id]["status"] = "failed"
            _jobs[job_id]["error"] = str(exc)


@router.post("/ingest", response_model=JobStatus, summary="Trigger ingestion for an uploaded file")
async def trigger_ingest(
    req: IngestRequest,
    user: dict = Depends(get_current_user),
) -> JobStatus:
    """Start the ingestion pipeline for a file that was just uploaded to MinIO."""
    if not settings.S3_BUCKET_NAME:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="S3_BUCKET_NAME is not configured.",
        )
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {"status": "pending", "stats": {}, "error": ""}

    t = threading.Thread(
        target=_run_ingest,
        args=(job_id, settings.S3_BUCKET_NAME, req.s3_key),
        daemon=True,
    )
    t.start()
    return JobStatus(job_id=job_id, status="pending")


@router.get("/jobs/{job_id}", response_model=JobStatus, summary="Poll ingestion job status")
async def get_job_status(
    job_id: str,
    user: dict = Depends(get_current_user),
) -> JobStatus:
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return JobStatus(job_id=job_id, **job)
