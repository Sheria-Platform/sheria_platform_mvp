"""Integration tests for POST /verify and GET /verify/history."""

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from tests.integration.conftest import build_app, make_token

# ── Constants ─────────────────────────────────────────────────────────────────

# The verify router registers POST "" so it must always be mounted with a prefix.
_PREFIX = "/verify"

_MOCK_REPORT = {
    "authentic": True,
    "confidence": 1.0,
    "document_type": "court_order",
    "extracted_metadata": {
        "court": "High Court",
        "judge": "Hon. Justice Oduol",
        "date": "2024-03-10",
        "parties": "Republic v Kamau",
        "case_number": "HC CR 45 OF 2024",
        "document_summary": "Bail ruling.",
    },
    "verification_checks": [
        {"check": "metadata_extraction", "passed": True, "detail": "ok"},
        {"check": "case_law_match", "passed": True, "detail": "ok"},
        {"check": "fraud_analysis", "passed": True, "detail": "ok"},
    ],
    "risk_flags": [],
    "summary": "Document appears authentic (confidence 100%).",
}


def _make_minimal_pdf() -> bytes:
    """Create a minimal valid PDF in memory using pypdf."""
    import io

    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=595, height=842)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _verify_app():
    """Build a test app with the verify router mounted under /verify."""
    from services.api.app.routes.verify import router

    return build_app(router, prefix=_PREFIX)


def _jwt_patch():
    """Patch jwt.settings for test token validation."""
    return patch("services.api.app.auth.jwt.settings", **{
        "JWT_SECRET_KEY": "test_secret_key_for_unit_tests_only_not_real",
        "JWT_ALGORITHM": "HS256",
    })


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_happy_path():
    """Valid PDF + auth → 200 with VerificationReport."""
    app = _verify_app()
    token = make_token()

    with (
        patch(
            "services.api.app.routes.verify.verify_document",
            new=AsyncMock(return_value=json.dumps(_MOCK_REPORT)),
        ),
        patch(
            "services.api.app.auth.jwt.is_blacklisted",
            new=AsyncMock(return_value=False),
        ),
        patch("services.api.app.routes.verify.postgres_memory") as mock_mem,
        _jwt_patch(),
    ):
        mock_mem.save_verification = AsyncMock()
        pdf_bytes = _make_minimal_pdf()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"{_PREFIX}",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("order.pdf", pdf_bytes, "application/pdf")},
                data={"document_type": "court_order", "case_number": "HC CR 45 OF 2024"},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert body["authentic"] is True
    assert body["confidence"] == 1.0


@pytest.mark.asyncio
async def test_verify_empty_file_returns_400():
    """Uploading an empty file (0 bytes) must return 400."""
    app = _verify_app()
    token = make_token()

    with (
        patch(
            "services.api.app.auth.jwt.is_blacklisted",
            new=AsyncMock(return_value=False),
        ),
        _jwt_patch(),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"{_PREFIX}",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("empty.pdf", b"", "application/pdf")},
            )

    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_verify_non_pdf_bytes_returns_400():
    """Uploading a non-PDF binary must return 400 with a parse error message."""
    app = _verify_app()
    token = make_token()

    with (
        patch(
            "services.api.app.auth.jwt.is_blacklisted",
            new=AsyncMock(return_value=False),
        ),
        _jwt_patch(),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"{_PREFIX}",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("fake.pdf", b"THIS IS NOT A PDF", "application/pdf")},
            )

    assert resp.status_code == 400
    detail = resp.json()["detail"].lower()
    assert "parse" in detail or "pdf" in detail


@pytest.mark.asyncio
async def test_verify_oversized_file_returns_413():
    """File exceeding MAX_PDF_UPLOAD_MB must return 413."""
    app = _verify_app()
    token = make_token()

    # Set limit to 1 MB for the test, send ~1.1 MB
    oversized = b"0" * (1 * 1024 * 1024 + 1024)

    with (
        patch(
            "services.api.app.auth.jwt.is_blacklisted",
            new=AsyncMock(return_value=False),
        ),
        patch("services.api.app.routes.verify.settings") as mock_route_settings,
        _jwt_patch(),
    ):
        mock_route_settings.MAX_PDF_UPLOAD_MB = 1

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"{_PREFIX}",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": ("big.pdf", oversized, "application/pdf")},
            )

    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_verify_history_returns_records():
    """GET /history with valid JWT returns user's verification history."""
    app = _verify_app()
    token = make_token(user_id="user-001")
    history = [
        {"id": "v1", "filename": "order.pdf", "authentic": True, "confidence": 1.0}
    ]

    with (
        patch(
            "services.api.app.auth.jwt.is_blacklisted",
            new=AsyncMock(return_value=False),
        ),
        patch("services.api.app.routes.verify.postgres_memory") as mock_mem,
        _jwt_patch(),
    ):
        mock_mem.get_user_verifications = AsyncMock(return_value=history)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                f"{_PREFIX}/history",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert resp.status_code == 200
    assert resp.json() == history


@pytest.mark.asyncio
async def test_verify_history_without_jwt_returns_401():
    """GET /history without Authorization header must return 401."""
    app = _verify_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(f"{_PREFIX}/history")

    assert resp.status_code == 401
