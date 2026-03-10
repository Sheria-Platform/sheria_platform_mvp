"""Tests for SemanticCache — vector reuse and TTL filtering."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_get_cached_response_returns_vector_on_miss(sample_vector):
    """Cache miss must return (None, vector) so the vector can be reused downstream."""
    with patch("services.api.app.cache.semantic.embeddings_client") as mock_embed, \
         patch("services.api.app.cache.semantic.qdrant_client") as mock_qdrant:
        mock_embed.embed_query = AsyncMock(return_value=sample_vector)
        mock_qdrant.client.search = AsyncMock(return_value=[])

        from services.api.app.cache.semantic import SemanticCache
        cache = SemanticCache()
        answer, vector = await cache.get_cached_response("test query")

    assert answer is None
    assert vector == sample_vector  # vector returned even on miss


@pytest.mark.asyncio
async def test_get_cached_response_returns_tuple_on_hit(sample_vector):
    """Cache hit must return (answer_str, vector)."""
    mock_hit = MagicMock()
    mock_hit.score = 0.98
    mock_hit.payload = {"answer": "cached answer", "created_at": 9999999999.0}

    with patch("services.api.app.cache.semantic.embeddings_client") as mock_embed, \
         patch("services.api.app.cache.semantic.qdrant_client") as mock_qdrant:
        mock_embed.embed_query = AsyncMock(return_value=sample_vector)
        mock_qdrant.client.search = AsyncMock(return_value=[mock_hit])

        from services.api.app.cache.semantic import SemanticCache
        cache = SemanticCache()
        answer, vector = await cache.get_cached_response("test query")

    assert answer == "cached answer"
    assert vector == sample_vector


@pytest.mark.asyncio
async def test_set_cached_response_skips_embed_if_vector_provided(sample_vector):
    """set_cached_response must NOT call embed_query when a vector is already provided."""
    with patch("services.api.app.cache.semantic.embeddings_client") as mock_embed, \
         patch("services.api.app.cache.semantic.qdrant_client") as mock_qdrant:
        mock_embed.embed_query = AsyncMock(return_value=sample_vector)
        mock_qdrant.client.upsert = AsyncMock()

        from services.api.app.cache.semantic import SemanticCache
        cache = SemanticCache()
        await cache.set_cached_response("test query", "test answer", vector=sample_vector)

    mock_embed.embed_query.assert_not_called()


@pytest.mark.asyncio
async def test_set_cached_response_embeds_when_no_vector(sample_vector):
    """set_cached_response must call embed_query when no vector is provided."""
    with patch("services.api.app.cache.semantic.embeddings_client") as mock_embed, \
         patch("services.api.app.cache.semantic.qdrant_client") as mock_qdrant:
        mock_embed.embed_query = AsyncMock(return_value=sample_vector)
        mock_qdrant.client.upsert = AsyncMock()

        from services.api.app.cache.semantic import SemanticCache
        cache = SemanticCache()
        await cache.set_cached_response("test query", "test answer")

    mock_embed.embed_query.assert_called_once_with("test query")
