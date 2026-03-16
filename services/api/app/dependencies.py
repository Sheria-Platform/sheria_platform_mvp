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
from services.api.app.memory.chat_repository import ChatRepository
from services.api.app.memory.chat_repository import chat_repository as _global_chat
from services.api.app.memory.feedback_repository import FeedbackRepository
from services.api.app.memory.feedback_repository import (
    feedback_repository as _global_feedback,
)
from services.api.app.memory.ingestion_repository import IngestionRepository
from services.api.app.memory.ingestion_repository import (
    ingestion_repository as _global_ingestion,
)
from services.api.app.memory.postgres import PostgresMemory
from services.api.app.memory.postgres import postgres_memory as _global_memory
from services.api.app.memory.prediction_repository import PredictionRepository
from services.api.app.memory.prediction_repository import (
    prediction_repository as _global_prediction,
)
from services.api.app.memory.user_repository import UserRepository
from services.api.app.memory.user_repository import user_repository as _global_user
from services.api.app.memory.verification_repository import VerificationRepository
from services.api.app.memory.verification_repository import (
    verification_repository as _global_verification,
)


def get_semantic_cache() -> SemanticCache:
    return _global_cache


def get_memory() -> PostgresMemory:
    return _global_memory


def get_llm_client() -> OllamaClient:
    return _global_llm


def get_chat_repo() -> ChatRepository:
    return _global_chat


def get_user_repo() -> UserRepository:
    return _global_user


def get_ingestion_repo() -> IngestionRepository:
    return _global_ingestion


def get_verification_repo() -> VerificationRepository:
    return _global_verification


def get_prediction_repo() -> PredictionRepository:
    return _global_prediction


def get_feedback_repo() -> FeedbackRepository:
    return _global_feedback
