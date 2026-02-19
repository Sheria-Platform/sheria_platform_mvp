# services/api/app/memory/postgres.py
from typing import Sequence

from sqlalchemy import select

from services.api.app.models.rag import ChatHistory
from services.api.app.core.database import get_db


class PostgresMemory:
    """
    Manager for persisting conversation state.
    """

    @staticmethod
    async def add_message(session_id: str, role: str, content: str, user_id: str):
        db_session = get_db()
        msg = ChatHistory(
            session_id=session_id,
            role=role,
            content=content,
            user_id=user_id,
        )
        db_session.add(msg)

        await db_session.commit()

    @staticmethod
    async def get_history(
            session_id: str,
            limit: int = 10,
    ) -> Sequence[ChatHistory]:
        """Retrieve the most recent *limit* messages for a session.

        Messages are returned in chronological order (oldest first)
        to match the format expected by LLM ``messages`` lists.

        Args:
            session_id: The conversation thread identifier.
            limit: Maximum number of messages to return.  Fetches the
                *newest* ``limit`` rows, then reverses them.

        Returns:
            A sequence of ``ChatHistory`` ORM objects ordered oldest
            to newest.
        """
        db_session = get_db()
        result = await db_session.execute(
            select(ChatHistory)
            .where(ChatHistory.session_id == session_id)
            .order_by(ChatHistory.created_at.desc())
            .limit(limit)
        )
        # Reverse to get chronological order (Oldest -> Newest)
        return result.scalars().all()[::-1]


postgres_memory = PostgresMemory()
