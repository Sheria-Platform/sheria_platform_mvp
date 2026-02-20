# services/api/app/routes/chat.py
import logging
from typing import Dict, Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, status, HTTPException
from fastapi.responses import StreamingResponse
from fastapi_restful.cbv import cbv
from sqlalchemy.ext.asyncio.session import AsyncSession

# Import classes for type hinting
from services.api.app.cache.semantic import SemanticCache
from services.api.app.clients.ollama_client import OllamaClient  # Replaces RayLLMClient
from services.api.app.core.database import get_db
from services.api.app.schema.chat import ChatRequest
from services.api.app.services.auth import get_current_user
from services.api.app.services.dependencies import get_memory
from services.api.app.services.dependencies import get_semantic_cache, get_llm_client
from services.api.app.services.rag import manage_conversations, ConversationCRUDManager

ROUTER_PREFIX = 'rag'

conversations_router = APIRouter(
    prefix=f"/{ROUTER_PREFIX}/conversations",
    tags=["rag"],
    redirect_slashes=False
)

logger = logging.getLogger(__name__)


@cbv(conversations_router)
class RagConversationAPI:
    cache: SemanticCache = Depends(get_semantic_cache)
    memory: ConversationCRUDManager = Depends(get_memory)
    llm: OllamaClient = Depends(get_llm_client)
    user: Dict = Depends(get_current_user)
    db_session: AsyncSession = Depends(get_db)
    background_tasks: BackgroundTasks

    @conversations_router.post('/chat/{conversation_id}', status_code=status.HTTP_200_OK)
    async def chat(self, conversation_id: str, data: ChatRequest):
        try:
            if conversation_id == 'new':
                data.conversation_id = None

            generator = await manage_conversations(
                data_in=data,
                user_data=self.user,
                memory=self.memory,
                llm=self.llm,
                cache=self.cache,
                background_tasks=self.background_tasks,
            )

            headers = {
                'X-Conversation-Id': str(data.conversation_id),
                "Access-Control-Expose-Headers": "X-Conversation-Id"
            }

            return StreamingResponse(
                generator,
                media_type="text/plain",
                headers=headers
            )

        except Exception as e:
            logger.error(f"Error processing chat request: {e}")

            raise HTTPException(detail=str(
                e), status_code=status.HTTP_400_BAD_REQUEST)
