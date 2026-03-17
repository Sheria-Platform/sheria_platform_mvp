"""Unit tests for the retriever node — jurisdiction filter and citations."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────


def _make_qdrant_result(text: str, court: str = "Supreme Court", score: float = 0.88):
    r = MagicMock()
    r.score = score
    r.payload = {
        "text": text,
        "citation_code": "[2023] KESC 45",
        "court_name": court,
        "year": "2023",
        "case_slug": "muiruri-v-republic-2023",
    }
    return r


def _make_state(jurisdiction_filter=None, query_vector=None):
    return {
        "current_query": "adverse possession Kenya",
        "query_vector": query_vector or [],
        "jurisdiction_filter": jurisdiction_filter or [],
        "messages": [],
    }


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_jurisdiction_filter_is_applied_to_qdrant_call():
    """When jurisdiction_filter is set, qdrant_client.search must receive a Filter."""
    from qdrant_client.http import models as qdrant_models

    sample_vector = [0.0] * 768
    state = _make_state(
        jurisdiction_filter=["Supreme Court"],
        query_vector=sample_vector,
    )

    with (
        patch(
            "services.api.app.agents.nodes.retriever.embeddings_client"
        ) as mock_embed,
        patch("services.api.app.agents.nodes.retriever.qdrant_client") as mock_qdrant,
        patch("services.api.app.agents.nodes.retriever.neo4j_client") as mock_neo4j,
    ):
        mock_embed.embed_query = AsyncMock(return_value=sample_vector)
        mock_qdrant.search = AsyncMock(return_value=[])
        mock_neo4j.query = AsyncMock(return_value=[])

        from services.api.app.agents.nodes.retriever import retrieve_node

        await retrieve_node(state)

    call_kwargs = mock_qdrant.search.call_args.kwargs
    q_filter = call_kwargs.get("query_filter")
    assert q_filter is not None
    assert isinstance(q_filter, qdrant_models.Filter)
    must = q_filter.must
    assert len(must) == 1
    assert must[0].key == "court_name"
    assert must[0].match.any == ["Supreme Court"]


@pytest.mark.asyncio
async def test_no_jurisdiction_filter_passes_none_to_qdrant():
    """Empty jurisdiction_filter → qdrant_client.search called with query_filter=None."""
    sample_vector = [0.0] * 768
    state = _make_state(jurisdiction_filter=[], query_vector=sample_vector)

    with (
        patch(
            "services.api.app.agents.nodes.retriever.embeddings_client"
        ) as mock_embed,
        patch("services.api.app.agents.nodes.retriever.qdrant_client") as mock_qdrant,
        patch("services.api.app.agents.nodes.retriever.neo4j_client") as mock_neo4j,
    ):
        mock_embed.embed_query = AsyncMock(return_value=sample_vector)
        mock_qdrant.search = AsyncMock(return_value=[])
        mock_neo4j.query = AsyncMock(return_value=[])

        from services.api.app.agents.nodes.retriever import retrieve_node

        await retrieve_node(state)

    call_kwargs = mock_qdrant.search.call_args.kwargs
    assert call_kwargs.get("query_filter") is None


@pytest.mark.asyncio
async def test_citations_populated_from_qdrant_results():
    """Structured citations must be returned in state['citations'] for each Qdrant hit."""
    sample_vector = [0.0] * 768
    state = _make_state(query_vector=sample_vector)

    hits = [
        _make_qdrant_result("Adverse possession requires 12 years."),
        _make_qdrant_result("Open and notorious possession required.", court="Court of Appeal"),
    ]

    with (
        patch(
            "services.api.app.agents.nodes.retriever.embeddings_client"
        ) as mock_embed,
        patch("services.api.app.agents.nodes.retriever.qdrant_client") as mock_qdrant,
        patch("services.api.app.agents.nodes.retriever.neo4j_client") as mock_neo4j,
    ):
        mock_embed.embed_query = AsyncMock(return_value=sample_vector)
        mock_qdrant.search = AsyncMock(return_value=hits)
        mock_neo4j.query = AsyncMock(return_value=[])

        from services.api.app.agents.nodes.retriever import retrieve_node

        result = await retrieve_node(state)

    assert "citations" in result
    assert len(result["citations"]) == 2
    assert result["citations"][0]["citation_code"] == "[2023] KESC 45"
    assert result["citations"][0]["court_name"] == "Supreme Court"
    assert result["citations"][1]["court_name"] == "Court of Appeal"


@pytest.mark.asyncio
async def test_retriever_does_not_overwrite_citations_on_graph_only_hits():
    """Graph search results appear in documents but NOT in citations (citations = Qdrant only)."""
    sample_vector = [0.0] * 768
    state = _make_state(query_vector=sample_vector)

    with (
        patch(
            "services.api.app.agents.nodes.retriever.embeddings_client"
        ) as mock_embed,
        patch("services.api.app.agents.nodes.retriever.qdrant_client") as mock_qdrant,
        patch("services.api.app.agents.nodes.retriever.neo4j_client") as mock_neo4j,
    ):
        mock_embed.embed_query = AsyncMock(return_value=sample_vector)
        mock_qdrant.search = AsyncMock(return_value=[])  # no Qdrant hits
        mock_neo4j.query = AsyncMock(
            return_value=[{"text": "Muiruri v Republic CITES adverse_possession"}]
        )

        from services.api.app.agents.nodes.retriever import retrieve_node

        result = await retrieve_node(state)

    # Graph result is in documents
    assert any("Muiruri" in d for d in result["documents"])
    # But citations list is empty (Qdrant returned nothing)
    assert result["citations"] == []
