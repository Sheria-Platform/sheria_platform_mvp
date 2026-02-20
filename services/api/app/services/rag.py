import asyncio
import json
import logging
import random
from typing import Dict, Sequence

from fastapi import BackgroundTasks
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.agents.graph import agent_app
from services.api.app.agents.state import AgentState
from services.api.app.cache.semantic import SemanticCache
from services.api.app.clients.ollama_client import OllamaClient
from services.api.app.models.rag import Messages, Conversations
from services.api.app.schema.chat import ChatRequest
from services.api.app.services.background import run_background_tasks

logger = logging.getLogger(__name__)


class ConversationCRUDManager:
    """
    Manages CRUD operations for conversations and messages in the database.
    
    This class provides methods to create, retrieve, and update conversations
    and their associated messages using an async database session.
    """

    def __init__(self, db_session: AsyncSession):
        """
        Initialize the ConversationCRUDManager with a database session.
        
        Args:
            db_session (AsyncSession): An async SQLAlchemy database session for executing queries.
        """
        self.db_session = db_session

    async def add_message(self, conversation_id: str, role: str, content: str):
        """
        Add a new message to a conversation.
        
        Creates a new message record and commits it to the database.
        
        Args:
            conversation_id (str): The unique identifier of the conversation.
            role (str): The role of the message sender (e.g., "user" or "assistant").
            content (str): The text content of the message.
        
        Returns:
            None
        """
        message = Messages(
            conversation_id=conversation_id,
            role=role,
            content=content
        )
        self.db_session.add(message)

        await self.db_session.commit()

    async def get_history(
            self,
            conversation_id: str,
            limit: int = 10,
    ) -> Sequence[Messages]:
        """
        Retrieve the message history for a conversation.
        
        Fetches messages in chronological order (oldest to newest) up to the specified limit.
        
        Args:
            conversation_id (str): The unique identifier of the conversation.
            limit (int, optional): The maximum number of messages to retrieve. Defaults to 10.
        
        Returns:
            Sequence[Messages]: A sequence of Message objects in chronological order.
        """

        result = await self.db_session.execute(
            select(
                Messages
            ).where(
                Messages.conversation_id == conversation_id
            ).order_by(
                Messages.created_at.desc()
            ).limit(
                limit
            )
        )
        # Reverse to get chronological order (Oldest -> Newest)
        return result.scalars().all()

    async def get_or_create_conversation(
            self,
            user_id: str,
            conversation_id: str | None = None
    ) -> Conversations:
        """
        Retrieve an existing conversation or create a new one.
        
        If a conversation_id is provided, retrieves the conversation ensuring it belongs
        to the specified user. If no conversation_id is provided, creates a new conversation
        for the user.
        
        Args:
            user_id (str): The unique identifier of the user.
            conversation_id (str | None, optional): The unique identifier of the conversation
                to retrieve. If None, a new conversation is created. Defaults to None.
        
        Returns:
            Conversations: The retrieved or newly created Conversation object.
        
        Raises:
            LookupError: If the conversation_id is provided but no matching conversation
                is found for the specified user.
        """
        if conversation_id:
            # Critical: Filter by user_id to prevent data leakage
            result = await self.db_session.execute(
                select(Conversations).where(
                    Conversations.id == conversation_id,
                    Conversations.user_id == user_id
                )
            )
            conversation = result.scalar_one_or_none()

            if not conversation:
                raise LookupError(f'Conversation not found: {conversation_id} for user {user_id}!')

            return conversation

        new_conversation = Conversations(
            title="New Conversation",
            user_id=user_id
        )
        self.db_session.add(new_conversation)
        await self.db_session.commit()

        return new_conversation

    async def update_conversation_title(self, conversation_id: str, new_title: str, user_id: str):
        """
        Update the title of an existing conversation.
        
        Updates the conversation title ensuring the conversation belongs to the specified user.
        
        Args:
            conversation_id (str): The unique identifier of the conversation to update.
            new_title (str): The new title to set for the conversation.
            user_id (str): The unique identifier of the user who owns the conversation.
        
        Returns:
            None
        """
        statement = (
            update(Conversations)
            .where(Conversations.id == conversation_id,
                   Conversations.user_id == user_id)
            .values(title=new_title)
        )
        await self.db_session.execute(statement)
        await self.db_session.commit()


async def manage_conversations(data_in: ChatRequest,
                               user_data: Dict,
                               memory: ConversationCRUDManager,
                               llm: OllamaClient,
                               cache: SemanticCache,
                               background_tasks: BackgroundTasks):
    """
    Manage chat conversations with caching, history, and streaming responses.
    
    This function orchestrates the entire conversation flow, including retrieving or creating
    conversations, checking for cached responses, managing conversation history, and streaming
    AI-generated responses. It handles both cached and live responses, automatically saving
    messages to the database and updating conversation titles for new conversations.
    
    Args:
        data_in (ChatRequest): The incoming chat request containing the user's query and
            optional conversation_id.
        user_data (Dict): A dictionary containing user authentication data, including the
            user's unique identifier under the 'sub' key.
        memory (ConversationCRUDManager): The conversation manager for database operations,
            used to create, retrieve, and update conversations and messages.
        llm (OllamaClient): The language model client used to generate AI responses when
            no cached response is available.
        cache (SemanticCache): The semantic cache for storing and retrieving previously
            generated responses to similar queries.
        background_tasks (BackgroundTasks): FastAPI background tasks manager for executing
            asynchronous operations like saving messages and updating conversation titles
            without blocking the response stream.
    
    Returns:
        AsyncGenerator: An async generator function that yields response content chunks.
            For cached responses, it simulates streaming by yielding small chunks with delays.
            For live responses, it yields tokens as they are generated by the language model.
            In case of errors, it yields a JSON-formatted error message.
    """
    user_query = data_in.query
    conversation_id = data_in.conversation_id

    is_first_conversation = False

    if not conversation_id:
        is_first_conversation = True

    user_id = user_data.get('sub')

    conversation_instance = await memory.get_or_create_conversation(conversation_id=conversation_id, user_id=user_id)
    conversation_id = str(conversation_instance.id)
    data_in.conversation_id = conversation_id

    if is_first_conversation:
        background_tasks.add_task(
            run_background_tasks,
            task_type='update_title',
            **{'conversation_id': conversation_id,
               'user_query': user_query,
               'user_id': user_id}
        )

    cached_answer = await cache.get_cached_response(user_query)

    if cached_answer:
        async def stream_cache():
            """
            The logic below is for aesthetic effect only, to simulate the typing feeling for the user. You can just
            yield the whole cache string once if you don't want the streaming simulation
            
            Stream a cached response in small chunks to simulate typing effect.
    
            This async generator function simulates a streaming response by breaking down
            a cached answer into random-sized chunks and yielding them with small delays
            between each chunk. This creates a typing effect for better user experience,
            making cached responses feel more natural and consistent with live responses.
            
            The function uses random chunk sizes (1-5 characters) and random delays
            (0.01-0.04 seconds) to create a realistic typing simulation. For applications
            that don't require this aesthetic effect, the entire cached_answer string
            can be yielded at once instead.
            
            Yields:
                str: Small chunks of the cached answer string, yielded sequentially with
                    random delays to simulate typing.
            
            Note:
                This function accesses the 'cached_answer' variable from the enclosing scope.
            """
            i = 0
            while i < len(cached_answer):
                chunk_size = random.randint(1, 5)
                chunk = cached_answer[i: i + chunk_size]

                yield chunk

                i += chunk_size

                await asyncio.sleep(random.uniform(0.01, 0.04))

        background_tasks.add_task(
            run_background_tasks,
            task_type='add_message',
            **{'conversation_id': conversation_id, 'role': "user", 'content': user_query}
        )
        background_tasks.add_task(
            run_background_tasks,
            task_type='add_message',
            **{'conversation_id': conversation_id, 'role': "assistant", 'content': cached_answer}
        )

        return stream_cache()

    conversation_history = await memory.get_history(conversation_id, limit=6)
    history_dicts = [{"role": msg.role, "content": msg.content} for msg in conversation_history]
    formatted_messages = []
    for msg in history_dicts[:-1]:
        if msg["role"] == "user":
            formatted_messages.append(HumanMessage(content=msg["content"]))
            
        elif msg["role"] == "assistant":
            formatted_messages.append(AIMessage(content=msg["content"]))
            
        elif msg["role"] == "system":
            formatted_messages.append(SystemMessage(content=msg["content"]))

    formatted_messages.append(HumanMessage(content=user_query))

    initial_state = AgentState(
        messages=formatted_messages,
        current_query=user_query,
        documents=[],
        plan=[],
        action="",
        tool_choice="",
        tool_input="",
    )

    async def stream_response():
        """
            Stream a live AI-generated response and save the conversation to the database.

            This async generator function streams tokens from the agent application as they are
            generated, accumulating them into a final answer. Once the complete response is
            received, it schedules background tasks to save both the user query and assistant
            response to the database, and caches the response for future similar queries.

            The function processes events from the agent application's event stream, specifically
            looking for "llm_token" custom events that contain content tokens to yield. After
            streaming is complete, it performs post-processing tasks including message persistence
            and cache updates.

            Yields:
                str: Individual content tokens from the AI response as they are generated, or
                    a JSON-formatted error message if an exception occurs during streaming.

            Returns:
                None: This is an async generator function that yields values but doesn't return.

            Raises:
                Exception: Any exceptions during streaming are caught, logged, and converted to
                    error messages that are yielded to the client.

            Note:
                This function accesses variables from the enclosing scope including:
                - initial_state: The agent's initial state configuration
                - llm: The language model client
                - user_id: The current user's identifier
                - conversation_id: The current conversation's identifier
                - user_query: The user's input query
                - background_tasks: FastAPI background tasks manager
                - cache: The semantic cache instance
            """
        final_answer = ''
        try:
            async for event in agent_app.astream_events(
                    initial_state,
                    config={
                        "configurable": {
                            "llm": llm,
                            "user_id": user_id
                        }
                    },
                    version='v2'
            ):
                kind = event['event']
                if kind == "on_custom_event" and event.get("name") == "llm_token":
                    content = event["data"].get("content")
                    if content:
                        yield content

                        final_answer += content

                elif kind == "on_chain_start":
                    pass

            if final_answer:
                background_tasks.add_task(
                    run_background_tasks,
                    task_type="add_message",
                    **{
                        'conversation_id': conversation_id,
                        'role': "user",
                        'content': user_query
                    }
                )
                background_tasks.add_task(
                    run_background_tasks,
                    task_type="add_message",
                    **{
                        'conversation_id': conversation_id,
                        'role': "assistant",
                        'content': final_answer
                    }
                )
                await cache.set_cached_response(user_query, final_answer)

        except Exception as e:
            logger.error("Error in chat stream: %s", e, exc_info=True)
            yield json.dumps(
                {"type": "error", "content": "An internal error occurred."}
            ) + "\n"

    return stream_response()

