# pipelines/ingestion/server.py
"""
Sheria Ingestion API Server

Lightweight FastAPI server that exposes HTTP endpoints for triggering and
monitoring ingestion jobs. Designed to run alongside the ingestion pipeline
inside the internal service mesh (no JWT auth required — protected by
network policy). An optional X-API-Key header is supported.

Endpoints:
    POST /ingest/trigger       - Trigger ingestion for a MinIO bucket/prefix
    POST /ingest/upload        - Upload a file → MinIO → ingest immediately
    GET  /ingest/jobs/{job_id} - Poll job status and final stats
    GET  /ingest/jobs          - List all jobs (most-recent first, max 100)
    GET  /health               - Liveness check

Running:
    uvicorn pipelines.ingestion.server:app --host 0.0.0.0 --port 8001
    # or directly:
    python -m pipelines.ingestion.server
"""

import io
import logging
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import (
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from minio import Minio
from pydantic import BaseModel, Field

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore[assignment]

from pipelines.ingestion.loaders.dispatcher import SUPPORTED_EXTENSIONS
from pipelines.ingestion.main import main, validate_config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# API-Key guard (optional)
# ---------------------------------------------------------------------------
API_KEY: str = os.getenv("INGEST_API_KEY", "")


def _check_api_key(x_api_key: str = Header(default="")) -> None:
    """Reject requests when INGEST_API_KEY is set and the header doesn't match."""
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ---------------------------------------------------------------------------
# In-memory job store (thread-safe)
# ---------------------------------------------------------------------------
_jobs: dict[str, dict[str, Any]] = {}
_jobs_lock = threading.Lock()

# Background executor — shared for the lifetime of the server process
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ingest-worker")


def _create_job(bucket_name: str, prefix: str) -> str:
    """Create a new job record and return its ID."""
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "pending",
            "bucket_name": bucket_name,
            "prefix": prefix,
            "created_at": time.time(),
            "completed_at": None,
            "duration_seconds": None,
            "stats": None,
            "error": None,
        }
    return job_id


def _run_job(job_id: str, bucket_name: str, prefix: str, kwargs: dict) -> None:
    """Run main() in a ThreadPoolExecutor thread and update the job record."""
    with _jobs_lock:
        _jobs[job_id]["status"] = "running"

    started_at = time.time()
    try:
        exit_code, stats = main(bucket_name, prefix, **kwargs)
        completed_at = time.time()
        with _jobs_lock:
            job = _jobs[job_id]
            job["status"] = "done" if exit_code == 0 else "failed"
            job["stats"] = stats
            job["completed_at"] = completed_at
            job["duration_seconds"] = round(completed_at - started_at, 2)
            if exit_code != 0:
                job["error"] = f"Pipeline exited with code {exit_code}"
    except Exception as exc:
        completed_at = time.time()
        logger.error(f"Job {job_id} raised an exception: {exc}", exc_info=True)
        with _jobs_lock:
            job = _jobs[job_id]
            job["status"] = "failed"
            job["error"] = str(exc)
            job["completed_at"] = completed_at
            job["duration_seconds"] = round(completed_at - started_at, 2)


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------
class TriggerRequest(BaseModel):
    bucket_name: str = Field(..., min_length=1, description="MinIO bucket name")
    prefix: str = Field(..., min_length=1, description="Object key prefix to ingest")
    max_workers: int | None = Field(None, ge=1, le=32)
    enable_graph: bool = Field(
        False, description="Enable Neo4j graph extraction (slow)"
    )
    file_batch_size: int | None = Field(None, ge=1, le=500)


class JobResponse(BaseModel):
    job_id: str
    status: str  # pending | running | done | failed
    bucket_name: str
    prefix: str
    created_at: float
    completed_at: float | None = None
    duration_seconds: float | None = None
    stats: dict[str, Any] | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    if load_dotenv is not None:
        load_dotenv()
    logger.info("Sheria Ingestion API started")
    yield
    logger.info("Sheria Ingestion API shutting down — draining background jobs…")
    _executor.shutdown(wait=False)


_HERE = Path(__file__).parent
templates = Jinja2Templates(directory=str(_HERE / "templates"))

app = FastAPI(
    title="Sheria Ingestion API",
    version="1.0.0",
    description=(
        "HTTP interface for triggering and monitoring the Sheria document ingestion pipeline. "
        "Accepts file uploads, triggers ingestion for existing MinIO prefixes, and exposes "
        "job status polling endpoints."
    ),
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")


def _job_age(created_at: float) -> str:
    delta = time.time() - created_at
    if delta < 60:
        return "just now"
    if delta < 3600:
        return f"{int(delta / 60)}m ago"
    return f"{int(delta / 3600)}h ago"


templates.env.globals["job_age"] = _job_age


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------
@app.get("/health", tags=["Health"])
async def health() -> dict[str, str]:
    """Liveness probe — always returns 200 when the server is up."""
    return {"status": "ok"}


@app.post(
    "/ingest/trigger",
    response_model=JobResponse,
    status_code=202,
    tags=["Ingestion"],
    summary="Trigger ingestion for an existing MinIO bucket/prefix",
)
async def trigger_ingestion(
    request: TriggerRequest,
    _: None = Depends(_check_api_key),
) -> dict[str, Any]:
    """
    Enqueue a background ingestion job for `bucket_name/prefix`.

    The job runs asynchronously. Poll `/ingest/jobs/{job_id}` to check progress.
    """
    job_id = _create_job(request.bucket_name, request.prefix)
    kwargs = {
        "enable_graph": request.enable_graph,
    }
    if request.max_workers is not None:
        kwargs["max_workers"] = request.max_workers
    if request.file_batch_size is not None:
        kwargs["file_batch_size"] = request.file_batch_size

    _executor.submit(_run_job, job_id, request.bucket_name, request.prefix, kwargs)

    with _jobs_lock:
        return dict(_jobs[job_id])


@app.post(
    "/ingest/upload",
    response_model=JobResponse,
    status_code=202,
    tags=["Ingestion"],
    summary="Upload a file to MinIO then ingest it immediately",
)
async def upload_and_ingest(
    file: UploadFile = File(
        ..., description="File to upload (PDF, DOCX, HTML, or TXT)"
    ),
    bucket_name: str = Form(default="api-uploads", description="Target MinIO bucket"),
    enable_graph: bool = Form(default=False, description="Enable graph extraction"),
    _: None = Depends(_check_api_key),
) -> dict[str, Any]:
    """
    Upload a single file, store it in MinIO, then trigger an ingestion job
    scoped to that object's prefix.

    The bucket is created automatically if it does not exist.
    """
    # Validate file extension
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type {suffix!r}. "
                f"Supported: {sorted(SUPPORTED_EXTENSIONS)}"
            ),
        )

    # Read file bytes (FastAPI UploadFile is async)
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")

    # Upload to MinIO
    try:
        config = validate_config()
        client = Minio(
            config["minio_endpoint"],
            access_key=config["minio_access_key"],
            secret_key=config["minio_secret_key"],
            secure=config["minio_secure"],
        )
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)

        object_name = f"api-uploads/{uuid.uuid4()}{suffix}"
        client.put_object(
            bucket_name,
            object_name,
            io.BytesIO(file_bytes),
            length=len(file_bytes),
            content_type=file.content_type or "application/octet-stream",
        )
        logger.info(f"Uploaded {file.filename!r} → s3://{bucket_name}/{object_name}")
    except Exception as exc:
        logger.error(f"MinIO upload failed: {exc}", exc_info=True)
        raise HTTPException(
            status_code=502, detail=f"MinIO upload failed: {exc}"
        ) from exc

    # Enqueue ingestion job scoped to the uploaded object's prefix
    job_id = _create_job(bucket_name, object_name)
    _executor.submit(
        _run_job,
        job_id,
        bucket_name,
        object_name,
        {"enable_graph": enable_graph},
    )

    with _jobs_lock:
        return dict(_jobs[job_id])


@app.get(
    "/ingest/jobs/{job_id}",
    response_model=JobResponse,
    tags=["Jobs"],
    summary="Get status and stats for a specific job",
)
async def get_job(
    job_id: str,
    _: None = Depends(_check_api_key),
) -> dict[str, Any]:
    """Return the current status and (when complete) final stats for `job_id`."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job {job_id!r} not found")
    return dict(job)


@app.get(
    "/ingest/jobs",
    response_model=list[JobResponse],
    tags=["Jobs"],
    summary="List all ingestion jobs (most-recent first, max 100)",
)
async def list_jobs(
    _: None = Depends(_check_api_key),
) -> list[dict[str, Any]]:
    """Return up to the 100 most-recently created ingestion jobs."""
    with _jobs_lock:
        jobs = sorted(_jobs.values(), key=lambda j: j["created_at"], reverse=True)
    return [dict(j) for j in jobs[:100]]


# ---------------------------------------------------------------------------
# UI Routes (no API-key guard, excluded from OpenAPI schema)
# ---------------------------------------------------------------------------
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(request: Request) -> HTMLResponse:
    """Serve the full dashboard page."""
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "api_key_enabled": bool(API_KEY),
            "supported_extensions": sorted(SUPPORTED_EXTENSIONS),
        },
    )


@app.get("/ui/jobs", response_class=HTMLResponse, include_in_schema=False)
async def ui_jobs(request: Request) -> HTMLResponse:
    """Return the jobs tbody fragment for htmx polling."""
    with _jobs_lock:
        jobs = sorted(_jobs.values(), key=lambda j: j["created_at"], reverse=True)
    return templates.TemplateResponse(
        "partials/jobs_table.html",
        {"request": request, "jobs": [dict(j) for j in jobs[:100]]},
    )


@app.post("/ui/trigger", response_class=HTMLResponse, include_in_schema=False)
async def ui_trigger(
    request: Request,
    bucket_name: str = Form(...),
    prefix: str = Form(...),
    max_workers: int | None = Form(default=None),
    enable_graph: str | None = Form(default=None),
    file_batch_size: int | None = Form(default=None),
) -> HTMLResponse:
    """Trigger ingestion from the UI form and return a job row fragment."""
    job_id = _create_job(bucket_name, prefix)
    kwargs: dict[str, Any] = {"enable_graph": enable_graph == "true"}
    if max_workers is not None:
        kwargs["max_workers"] = max_workers
    if file_batch_size is not None:
        kwargs["file_batch_size"] = file_batch_size

    _executor.submit(_run_job, job_id, bucket_name, prefix, kwargs)

    with _jobs_lock:
        job = dict(_jobs[job_id])

    return templates.TemplateResponse(
        "partials/job_row.html",
        {"request": request, "job": job, "error": None},
    )


@app.post("/ui/upload", response_class=HTMLResponse, include_in_schema=False)
async def ui_upload(
    request: Request,
    file: UploadFile = File(...),
    bucket_name: str = Form(default="api-uploads"),
    enable_graph: str | None = Form(default=None),
) -> HTMLResponse:
    """Upload a file from the UI form and return a job row fragment (or error row)."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        return templates.TemplateResponse(
            "partials/job_row.html",
            {
                "request": request,
                "job": None,
                "error": (
                    f"Unsupported file type {suffix!r}. "
                    f"Supported: {sorted(SUPPORTED_EXTENSIONS)}"
                ),
            },
        )

    file_bytes = await file.read()
    if not file_bytes:
        return templates.TemplateResponse(
            "partials/job_row.html",
            {"request": request, "job": None, "error": "Uploaded file is empty"},
        )

    try:
        config = validate_config()
        client = Minio(
            config["minio_endpoint"],
            access_key=config["minio_access_key"],
            secret_key=config["minio_secret_key"],
            secure=config["minio_secure"],
        )
        if not client.bucket_exists(bucket_name):
            client.make_bucket(bucket_name)

        object_name = f"api-uploads/{uuid.uuid4()}{suffix}"
        client.put_object(
            bucket_name,
            object_name,
            io.BytesIO(file_bytes),
            length=len(file_bytes),
            content_type=file.content_type or "application/octet-stream",
        )
        logger.info(f"UI upload: {file.filename!r} → s3://{bucket_name}/{object_name}")
    except Exception as exc:
        logger.error(f"MinIO upload failed: {exc}", exc_info=True)
        return templates.TemplateResponse(
            "partials/job_row.html",
            {"request": request, "job": None, "error": f"MinIO upload failed: {exc}"},
        )

    job_id = _create_job(bucket_name, object_name)
    _executor.submit(
        _run_job,
        job_id,
        bucket_name,
        object_name,
        {"enable_graph": enable_graph == "true"},
    )

    with _jobs_lock:
        job = dict(_jobs[job_id])

    return templates.TemplateResponse(
        "partials/job_row.html",
        {"request": request, "job": job, "error": None},
    )


# ---------------------------------------------------------------------------
# Direct execution entry-point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    uvicorn.run(
        "pipelines.ingestion.server:app",
        host=os.getenv("INGEST_HOST", "0.0.0.0"),
        port=int(os.getenv("INGEST_PORT", "8001")),
        reload=os.getenv("INGEST_RELOAD", "false").lower() == "true",
    )
