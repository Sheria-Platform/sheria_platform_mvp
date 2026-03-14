# services/api/app/dependencies.py
"""Shared FastAPI dependency providers.

These thin wrappers around the global singletons allow test suites to
override dependencies via ``app.dependency_overrides`` without importing
the singletons directly in every route.

Usage::

    from services.api.app.dependencies import get_semantic_cache, get_memory, get_llm_client
"""

from services.api.app.cache.semantic import SemanticCache
from services.api.app.cache.semantic import semantic_cache as _global_cache
from services.api.app.clients.ollama_client import OllamaClient
from services.api.app.clients.ollama_client import ollama_client as _global_llm
from services.api.app.memory.postgres import PostgresMemory
from services.api.app.memory.postgres import postgres_memory as _global_memory


def get_semantic_cache() -> SemanticCache:
    return _global_cache


def get_memory() -> PostgresMemory:
    return _global_memory


def get_llm_client() -> OllamaClient:
    return _global_llm
