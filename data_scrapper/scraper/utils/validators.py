"""File integrity validation, MIME detection, and duplicate checking."""

import hashlib
import mimetypes

# Magic byte signatures
_PDF_MAGIC = b"%PDF-"
_ZIP_MAGIC = b"PK\x03\x04"  # DOCX/XLSX are ZIP archives


def validate_pdf(content: bytes) -> bool:
    """Return True if `content` begins with the PDF magic bytes."""
    return content[:5] == _PDF_MAGIC


def validate_docx(content: bytes) -> bool:
    """Return True if `content` begins with ZIP magic bytes (DOCX/XLSX/ODP)."""
    return content[:4] == _ZIP_MAGIC


def compute_sha256(content: bytes) -> str:
    """Return hex-encoded SHA-256 digest of `content`."""
    return hashlib.sha256(content).hexdigest()


def detect_mime_type(content: bytes, filename: str) -> str:
    """
    Best-effort MIME detection: magic bytes first, then file extension.
    Returns a plain string like 'application/pdf'.
    """
    if content[:5] == _PDF_MAGIC:
        return "application/pdf"
    if content[:4] == _ZIP_MAGIC:
        # Could be docx/xlsx/pptx — use extension to disambiguate
        mime, _ = mimetypes.guess_type(filename)
        return mime or "application/zip"
    mime, _ = mimetypes.guess_type(filename)
    return mime or "application/octet-stream"


def is_duplicate(sha256: str, existing_hashes: set) -> bool:
    """Return True if `sha256` is already in `existing_hashes`."""
    return sha256 in existing_hashes
