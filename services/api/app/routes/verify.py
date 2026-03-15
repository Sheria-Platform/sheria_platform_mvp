# services/api/app/routes/verify.py
"""Sheria Verify — court document authentication endpoint.

POST /api/v1/verify
    Accepts a multipart PDF upload, extracts its text with pypdf,
    runs the ``verify_document`` tool (3-step LLM + Qdrant pipeline),
    and returns a ``VerificationReport``.

No streaming — document verification is a synchronous request/response.
"""

import json
import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from services.api.app.auth.jwt import get_current_user
from services.api.app.tools.verify_document import verify_document

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Response schema ───────────────────────────────────────────────────────────


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


# ── Helpers ───────────────────────────────────────────────────────────────────


def _extract_text_from_pdf(pdf_bytes: bytes) -> str:
    """Extract plain text from PDF bytes using pypdf.

    Tries the standard text-layer extraction.  If that yields nothing
    (scanned/image-only PDF), returns an empty string — the LLM steps
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


# ── Endpoint ──────────────────────────────────────────────────────────────────


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
async def verify_court_document(
    file: UploadFile = File(..., description="PDF court document to verify"),
    document_type: str = Form(
        default="court_order",
        description="Type of document: court_order | judgment | pleading | affidavit",
    ),
    case_number: str = Form(
        default="",
        description="Case reference number as it appears on the document",
    ),
    user: dict = Depends(get_current_user),
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

    # ── Read & validate PDF ───────────────────────────────────────────────
    pdf_bytes = await file.read()

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
            "No text extracted from PDF — likely a scanned image document",
            extra={"upload_filename": file.filename},
        )

    # ── Run verification pipeline ─────────────────────────────────────────
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

    return VerificationReport(**report_data)
