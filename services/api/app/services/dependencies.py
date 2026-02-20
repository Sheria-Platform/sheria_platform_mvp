from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.core.database import get_db
from services.api.app.services.rag import ConversationCRUDManager

from services.api.app.cache.semantic import semantic_cache, SemanticCache
from services.api.app.clients.ollama_client import ollama_client, OllamaClient


async def get_memory(db: AsyncSession = Depends(get_db)) -> ConversationCRUDManager:
    return ConversationCRUDManager(db_session=db)


def get_semantic_cache() -> SemanticCache:
    return semantic_cache


def get_llm_client() -> OllamaClient:
    return ollama_client
