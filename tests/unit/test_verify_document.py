"""Unit tests for verify_document — mocks all external clients."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

_GOOD_METADATA = json.dumps({
    "court": "High Court of Kenya",
    "judge": "Hon. Justice Oduol",
    "date": "2024-03-10",
    "parties": "Republic v Kamau",
    "case_number": "HC CR 45 OF 2024",
    "document_summary": "Criminal case ruling on bail application.",
})

_GOOD_FRAUD = json.dumps({
    "fraud_indicators_found": False,
    "risk_level": "low",
    "flags": [],
    "analysis": "No forgery indicators detected.",
})

_TOOL_INPUT = json.dumps({
    "document_text": "IN THE HIGH COURT OF KENYA\nCASE NO. HC CR 45 OF 2024\nRepublic v Kamau",
    "document_type": "court_order",
    "case_number": "HC CR 45 OF 2024",
})


def _make_qdrant_hit(score: float = 0.92):
    hit = MagicMock()
    hit.score = score
    hit.payload = {"source": "kenya_law_reports/hc_cr_45_2024.pdf"}
    return hit


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_verify_document_happy_path():
    """All 3 checks pass → authentic=True, confidence=1.0."""
    with (
        patch("services.api.app.tools.verify_document.ollama_client") as mock_ollama,
        patch(
            "services.api.app.tools.verify_document.embeddings_client"
        ) as mock_embed,
        patch("services.api.app.tools.verify_document.qdrant_client") as mock_qdrant,
    ):
        mock_ollama.chat_completion = AsyncMock(
            side_effect=[_GOOD_METADATA, _GOOD_FRAUD]
        )
        mock_embed.embed_query = AsyncMock(return_value=[0.0] * 768)
        mock_qdrant.search = AsyncMock(return_value=[_make_qdrant_hit(0.92)])

        from services.api.app.tools.verify_document import verify_document

        result = json.loads(await verify_document(_TOOL_INPUT))

    assert result["authentic"] is True
    assert result["confidence"] == 1.0
    assert len(result["verification_checks"]) == 3
    assert all(c["passed"] for c in result["verification_checks"])


@pytest.mark.asyncio
async def test_verify_document_empty_text_still_returns_report():
    """Empty document_text must not crash — pipeline runs, metadata check fails."""
    tool_input = json.dumps({
        "document_text": "",
        "document_type": "judgment",
        "case_number": "",
    })
    with (
        patch("services.api.app.tools.verify_document.ollama_client") as mock_ollama,
        patch(
            "services.api.app.tools.verify_document.embeddings_client"
        ) as mock_embed,
        patch("services.api.app.tools.verify_document.qdrant_client") as mock_qdrant,
    ):
        # Metadata LLM returns empty fields → metadata_passed = False
        empty_meta = json.dumps({
            "court": "", "judge": "", "date": "",
            "parties": "", "case_number": "", "document_summary": "",
        })
        mock_ollama.chat_completion = AsyncMock(
            side_effect=[empty_meta, _GOOD_FRAUD]
        )
        mock_embed.embed_query = AsyncMock(return_value=[0.0] * 768)
        mock_qdrant.search = AsyncMock(return_value=[])

        from services.api.app.tools.verify_document import verify_document

        result = json.loads(await verify_document(tool_input))

    assert "authentic" in result
    assert "confidence" in result
    meta_check = next(c for c in result["verification_checks"] if c["check"] == "metadata_extraction")
    assert meta_check["passed"] is False


@pytest.mark.asyncio
async def test_verify_document_malformed_llm_json_does_not_crash():
    """If the LLM returns non-JSON, metadata step fails gracefully; others continue."""
    with (
        patch("services.api.app.tools.verify_document.ollama_client") as mock_ollama,
        patch(
            "services.api.app.tools.verify_document.embeddings_client"
        ) as mock_embed,
        patch("services.api.app.tools.verify_document.qdrant_client") as mock_qdrant,
    ):
        mock_ollama.chat_completion = AsyncMock(
            side_effect=["NOT VALID JSON {{{{", _GOOD_FRAUD]
        )
        mock_embed.embed_query = AsyncMock(return_value=[0.0] * 768)
        mock_qdrant.search = AsyncMock(return_value=[_make_qdrant_hit(0.92)])

        from services.api.app.tools.verify_document import verify_document

        result = json.loads(await verify_document(_TOOL_INPUT))

    assert "authentic" in result
    meta_check = next(c for c in result["verification_checks"] if c["check"] == "metadata_extraction")
    assert meta_check["passed"] is False


@pytest.mark.asyncio
async def test_verify_document_zero_qdrant_hits_lowers_confidence():
    """Zero Qdrant hits → case_law_match fails → confidence ≤ 0.60."""
    with (
        patch("services.api.app.tools.verify_document.ollama_client") as mock_ollama,
        patch(
            "services.api.app.tools.verify_document.embeddings_client"
        ) as mock_embed,
        patch("services.api.app.tools.verify_document.qdrant_client") as mock_qdrant,
    ):
        mock_ollama.chat_completion = AsyncMock(
            side_effect=[_GOOD_METADATA, _GOOD_FRAUD]
        )
        mock_embed.embed_query = AsyncMock(return_value=[0.0] * 768)
        mock_qdrant.search = AsyncMock(return_value=[])  # no hits

        from services.api.app.tools.verify_document import verify_document

        result = json.loads(await verify_document(_TOOL_INPUT))

    qdrant_check = next(c for c in result["verification_checks"] if c["check"] == "case_law_match")
    assert qdrant_check["passed"] is False
    assert result["confidence"] <= 0.60
