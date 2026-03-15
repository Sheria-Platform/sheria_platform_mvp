"""Tests for the retriever node — vector reuse and deduplication."""

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_retriever_skips_embed_when_vector_in_state(base_state, sample_vector):
    """Retriever must reuse state['query_vector'] and NOT call embed_query."""
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

        await retrieve_node(base_state)

    mock_embed.embed_query.assert_not_called()


@pytest.mark.asyncio
async def test_retriever_embeds_when_no_vector_in_state(sample_vector):
    """Retriever must call embed_query when query_vector is empty."""
    state = {
        "current_query": "test",
        "query_vector": [],  # empty → must embed
        "messages": [],
    }
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

    mock_embed.embed_query.assert_called_once_with("test")


def test_dedup_ignores_source_suffix():
    """Docs differing only by source attribution are treated as duplicates."""
    from services.api.app.agents.nodes.retriever import _dedup

    docs = [
        "Adverse possession requires 12 years. [Source: muiruri_v_republic.pdf]",
        "Adverse possession requires 12 years. [Source: different_doc.pdf]",
        "Unique content here. [Source: other.pdf]",
    ]
    result = _dedup(docs)
    assert len(result) == 2  # duplicate content collapsed


def test_dedup_preserves_original_string():
    """The original string (with source attribution) is preserved in the output."""
    from services.api.app.agents.nodes.retriever import _dedup

    docs = ["Some text. [Source: file.pdf]"]
    result = _dedup(docs)
    assert result[0] == "Some text. [Source: file.pdf]"
