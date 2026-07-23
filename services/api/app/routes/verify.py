# services/api/app/routes/verify.py
"""Sheria Verify -- court document authentication endpoint.

POST /api/v1/verify
    Accepts a multipart PDF upload, extracts its text with pypdf,
    runs the ``verify_document`` tool (3-step LLM + Qdrant pipeline),
    and returns a ``VerificationReport``.

No streaming -- document verification is a synchronous request/response.
"""

import json
import logging
from typing import Literal

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from pydantic import BaseModel

from services.api.app.auth.permissions import require_role
from services.api.app.config import settings
from services.api.app.dependencies import get_verification_repo
from services.api.app.limiter import limiter
from services.api.app.memory.verification_repository import VerificationRepository
from services.api.app.tools.verify_document import verify_document

logger = logging.getLogger(__name__)

router = APIRouter()


# -- Response schema -----------------------------------------------------------


class VerificationCheck(BaseModel):
    check: str
    passed: bool
    detail: str


class VerificationReport(BaseModel):
    authentic: bool
    confidence: float
    document_type: str
    extracted_metadata: dict
    verification_checks: list[VerificationCheck]
    risk_flags: list[str]
    summary: str


class VerificationActivity(BaseModel):
    id: int
    filename: str
    document_type: str
    case_number: str
    authentic: bool
    confidence: float
    report: VerificationReport
    created_at: str


# -- Helpers -------------------------------------------------------------------


def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract plain text from PDF bytes using pypdf.

    Tries the standard text-layer extraction.  If that yields nothing
    (scanned/image-only PDF), returns an empty string -- the LLM steps
    will still run but will note they could not read the document.

    Args:
        pdf_bytes: Raw PDF file content.

    Returns:
        Extracted text string (may be empty for image-only PDFs).

    Raises:
        ValueError: If ``pypdf`` cannot parse the bytes as a PDF.
    """
    try:
        import io

        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(pdf_bytes))
        pages: list[str] = []
        for page in reader.pages:
            text = page.extract_text() or ""
            pages.append(text)
        return "\n".join(pages).strip()
    except Exception as exc:
        raise ValueError(f"Could not parse PDF: {exc}") from exc


# -- Endpoint ------------------------------------------------------------------


@router.post(
    "",
    response_model=VerificationReport,
    summary="Verify a court document",
    description=(
        "Upload a PDF court document and receive an authenticity report. "
        "The pipeline extracts metadata via LLM, cross-references the case "
        "in Kenya Law Reports (Qdrant), and runs a fraud pattern analysis."
    ),
)
@limiter.limit("10/minute")
async def verify_court_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(..., description="PDF court document to verify"),
    document_type: Literal["court_order", "judgment", "pleading", "affidavit"] = Form(
        default="court_order",
        description="Type of court document being verified",
    ),
    case_number: str = Form(
        default="",
        description="Case reference number as it appears on the document",
    ),
    user: dict = Depends(require_role("registrar", "judge", "magistrate")),
    memory: VerificationRepository = Depends(get_verification_repo),
) -> VerificationReport:
    """Authenticate a court document and return a verification report.

    Args:
        file:          PDF file upload.
        document_type: Declared type of the document.
        case_number:   Optional case reference for Qdrant cross-referencing.
        user:          Authenticated user from JWT.

    Returns:
        ``VerificationReport`` with authenticity flag, confidence score,
        per-check results, risk flags, and a human-readable summary.

    Raises:
        HTTPException(400): If the uploaded file is not a valid PDF.
        HTTPException(422): If the verification pipeline raises an
            unrecoverable error.
    """
    logger.info(
        "Document verification requested",
        extra={
            "user_id": user.get("id"),
            "document_type": document_type,
            "case_number": case_number,
            "upload_filename": file.filename,
        },
    )

    # -- Read & validate PDF ---------------------------------------------------
    _max_bytes = settings.MAX_PDF_UPLOAD_MB * 1024 * 1024
    # Early rejection when Content-Length is present — avoids buffering large files
    if file.size is not None and file.size > _max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum allowed size is {settings.MAX_PDF_UPLOAD_MB} MB.",
        )
    pdf_bytes = await file.read()
    # Authoritative check (handles absent or spoofed Content-Length)
    if len(pdf_bytes) > _max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=(
                f"File too large. Maximum allowed size is "
                f"{settings.MAX_PDF_UPLOAD_MB} MB."
            ),
        )

    if not pdf_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    try:
        document_text = _extract_text_from_pdf(pdf_bytes)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    if not document_text:
        logger.warning(
            "No text extracted from PDF -- likely a scanned image document",
            extra={"upload_filename": file.filename},
        )

    # -- Run verification pipeline ---------------------------------------------
    tool_input = json.dumps(
        {
            "document_text": document_text,
            "document_type": document_type,
            "case_number": case_number,
        }
    )

    try:
        result_json = await verify_document(tool_input)
        report_data = json.loads(result_json)
    except Exception as exc:
        logger.error("Verification pipeline error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Verification failed: {exc}",
        ) from exc

    if "error" in report_data:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=report_data["error"],
        )

    report = VerificationReport(**report_data)

    background_tasks.add_task(
        memory.save_verification,
        user.get("id", ""),
        file.filename or "",
        document_type,
        case_number,
        report_data,
    )

    return report


# -- History endpoint ----------------------------------------------------------


@router.get(
    "/history",
    response_model=list[VerificationActivity],
    summary="List past document verifications",
    description="Return the authenticated user's verification history, newest first.",
)
async def get_verification_history(
    user: dict = Depends(require_role("registrar", "judge", "magistrate")),
    memory: VerificationRepository = Depends(get_verification_repo),
) -> list[VerificationActivity]:
    """Return verification activity records for the current user.

    Args:
        user:   Authenticated user from JWT.
        memory: Verification repository dependency.

    Returns:
        List of verification activity dicts, newest first (up to 50).
    """
    return await memory.get_user_verifications(user.get("id", ""))
