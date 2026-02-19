# services/api/app/memory/postgres.py
from typing import Sequence

from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.models.rag import ChatHistory
from services.api.app.core.database import get_db


class PostgresMemory:
    """
    Manager for persisting conversation state.
    """
    def __init__(self, db_session: AsyncSession):
        self.db_session = db_session

    async def add_message(self, session_id: str, role: str, content: str, user_id: str):
        msg = ChatHistory(
            session_id=session_id,
            role=role,
            content=content,
            user_id=user_id,
        )
        self.db_session.add(msg)

        await self.db_session.commit()

    async def get_history(
            self,
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
        result = await self.db_session.execute(
            select(ChatHistory)
            .where(ChatHistory.session_id == session_id)
            .order_by(ChatHistory.created_at.desc())
            .limit(limit)
        )
        # Reverse to get chronological order (Oldest -> Newest)
        return result.scalars().all()[::-1]
