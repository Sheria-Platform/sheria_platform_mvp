"""Shared fixtures for Sheria API unit tests."""
import os

# Set required env vars before any settings-dependent imports
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NEO4J_PASSWORD", "test_password")
os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key_for_unit_tests_only_not_real")

from unittest.mock import AsyncMock, MagicMock

import pytest

from services.api.app.agents.state import AgentState


# ── Shared mock fixtures ────────────────────────────────────────────────────

@pytest.fixture
def sample_vector() -> list[float]:
    """2560-dim zero vector matching nomic-embed-text dimensions."""
    return [0.0] * 2560


@pytest.fixture
def base_state(sample_vector) -> AgentState:
    """Minimal valid AgentState for unit tests."""
    return AgentState(
        messages=[{"role": "user", "content": "What is adverse possession?"}],
        documents=[],
        current_query="adverse possession Kenya",
        plan=[],
        action="retrieve",
        tool_choice="",
        tool_input="",
        query_vector=sample_vector,
    )


@pytest.fixture
def mock_embeddings_client(sample_vector):
    """Mock OllamaEmbeddingsClient returning a fixed vector."""
    client = MagicMock()
    client.embed_query = AsyncMock(return_value=sample_vector)
    return client


@pytest.fixture
def mock_qdrant_client():
    """Mock VectorDBClient returning empty results."""
    client = MagicMock()
    client.search = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_neo4j_client():
    """Mock Neo4jClient returning empty results."""
    client = MagicMock()
    client.query = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_ollama_client():
    """Mock OllamaClient returning a fixed JSON plan."""
    client = MagicMock()
    client.chat_completion = AsyncMock(
        return_value='{"action": "retrieve", "refined_query": "adverse possession Kenya", "reasoning": "test"}'
    )
    return client
