import json
import logging
from typing import Dict, Sequence

from fastapi import BackgroundTasks
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
    Manager for persisting conversation state.
    """
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def add_message(self, conversation_id: str, role: str, content: str):
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
        """Retrieve the most recent *limit* messages for a session.

        Messages are returned in chronological order (oldest first)
        to match the format expected by LLM ``messages`` lists.

        Args:
            conversation_id: The conversation thread identifier.
            limit: Maximum number of messages to return.  Fetches the
                *newest* ``limit`` rows, then reverses them.

        Returns:
            A sequence of ``ChatHistory`` ORM objects ordered oldest
            to newest.
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
        # 1. Logic for existing conversation
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
    user_query = data_in.query
    conversation_id = data_in.conversation_id

    is_first_conversation = False

    if not conversation_id:
        is_first_conversation = True

    user_id = user_data.get('sub')

    conversation_instance = await memory.get_or_create_conversation(conversation_id=conversation_id, user_id=user_id)
    conversation_id = str(conversation_instance.id)
    data_in.conversation_id = conversation_id

    cached_answer = await cache.get_cached_response(user_query)

    if cached_answer:
        async def stream_cache():
            yield json.dumps(
                {"type": "answer", "content": cached_answer, "conversation_id": conversation_id}
            ) + "\n"

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
    history_dicts.append({"role": "user", "content": user_query})

    if is_first_conversation:
        background_tasks.add_task(
            run_background_tasks,
            **{'conversation_id': conversation_id,
               'user_query': user_query,
               'user_id': user_id}
        )

    initial_state = AgentState(
        messages=history_dicts,
        current_query=user_query,
        documents=[],
        plan=[],
        action="direct_answer",
        tool_choice="",
        tool_input="",
    )

    async def stream_response():
        final_answer = ''
        try:
            async for event in agent_app.astream(
                    initial_state, config={"configurable": {"llm": llm, "user_id": user_id}}
            ):
                node_name = list(event.keys())[0]
                node_data = event[node_name]

                yield json.dumps(
                    {
                        "type": "status",
                        "node": node_name,
                        "session_id": conversation_id,
                        "info": f"Completed step: {node_name}",
                    }
                ) + "\n"

                if node_name == "responder":
                    if "messages" in node_data and node_data["messages"]:
                        ai_msg = node_data["messages"][-1]
                        final_answer = ai_msg.get("content", "")

                        yield json.dumps(
                            {
                                "type": "answer",
                                "content": final_answer,
                                "session_id": conversation_id,
                            }
                        ) + "\n"
            if final_answer:
                background_tasks.add_task(
                    task_type="add_message",
                    **{
                        'conversation_id': conversation_id,
                        'role': "user",
                        'content': user_query
                    }
                )
                background_tasks.add_task(
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
