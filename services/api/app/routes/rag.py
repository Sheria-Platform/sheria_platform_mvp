# services/api/app/routes/chat.py
import logging
from typing import Dict, Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, status, HTTPException
from fastapi.requests import Request
from fastapi.responses import StreamingResponse
from fastapi_restful.cbv import cbv
from sqlalchemy.ext.asyncio.session import AsyncSession

# Import classes for type hinting
from services.api.app.cache.semantic import SemanticCache
from services.api.app.clients.ollama_client import OllamaClient  # Replaces RayLLMClient
from services.api.app.core.database import get_db
from services.api.app.schema.pagination import Pagination, pagination_params
from services.api.app.schema.rag import ChatRequest
from services.api.app.services.auth import get_current_user
from services.api.app.services.dependencies import get_memory
from services.api.app.services.dependencies import get_semantic_cache, get_llm_client
from services.api.app.services.rag import manage_conversations, ConversationCRUDManager, fetch_conversation_messages, \
    fetch_conversations

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
            else:
                data.conversation_id = conversation_id

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

    @conversations_router.get('/list', status_code=status.HTTP_200_OK)
    async def get_conversations(self, request: Request,
                                _pagination_params: Pagination = Depends(pagination_params)):
        """
        Retrieve a paginated list of conversations for the authenticated user.

        This endpoint fetches all conversations associated with the current user,
        applying pagination parameters to control the number and ordering of results.
        The conversations are retrieved from the database and returned with pagination
        metadata.

        Args:
            request (Request): The FastAPI request object containing request metadata
                and context information.
            _pagination_params (Pagination, optional): Pagination parameters including
                page number, page size, and ordering preferences. Defaults to values
                provided by the pagination_params dependency.

        Returns:
            dict: A dictionary containing the paginated list of conversations along
                with pagination metadata such as total count, current page, and page size.

        Raises:
            HTTPException: A 400 Bad Request error if the conversation retrieval fails
                for any reason, with the exception details included in the response.
        """
        try:
            conversations = await fetch_conversations(
                db_session=self.db_session,
                pagination_params=_pagination_params,
                user_id=self.user.get('sub'),
                request=request
            )

            return conversations

        except Exception as e:
            logger.exception(
                f"Failed to retrieve conversation: {e}", exc_info=True)
            raise HTTPException(detail=str(
                e), status_code=status.HTTP_400_BAD_REQUEST)

    @conversations_router.get('/{conversation_id}', status_code=status.HTTP_200_OK)
    async def get_messages(self, conversation_id: str,
                           request: Request,
                           _pagination_params: Pagination = Depends(pagination_params)):
        """
        Retrieve a paginated list of messages for a specific conversation.

        This endpoint fetches all messages associated with a given conversation ID,
        applying pagination parameters to control the number and ordering of results.
        Messages are automatically ordered in ascending order (oldest first) and
        returned with pagination metadata.

        Args:
            conversation_id (str): The unique identifier of the conversation whose
                messages are to be retrieved.
            request (Request): The FastAPI request object containing request metadata
                and context information.
            _pagination_params (Pagination, optional): Pagination parameters including
                page number, page size, and ordering preferences. The ordering is
                automatically set to ascending ('asc') regardless of the input value.
                Defaults to values provided by the pagination_params dependency.

        Returns:
            dict: A dictionary containing the paginated list of messages along with
                pagination metadata such as total count, current page, and page size.

        Raises:
            HTTPException: A 400 Bad Request error if the message retrieval fails
                for any reason, with the exception details included in the response.
        """
        try:
            _pagination_params.ordering = 'asc'

            messages = await fetch_conversation_messages(
                db_session=self.db_session,
                pagination_params=_pagination_params,
                conversation_id=conversation_id,
                request=request
            )

            return messages

        except Exception as e:
            logger.exception(
                f"Failed to retrieve messages: {e}", exc_info=True)
            raise HTTPException(detail=str(
                e), status_code=status.HTTP_400_BAD_REQUEST)
