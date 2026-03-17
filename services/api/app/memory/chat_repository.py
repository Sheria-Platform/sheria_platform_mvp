# services/api/app/memory/chat_repository.py
"""Chat message persistence -- add, retrieve, and list conversation sessions."""

from collections.abc import Sequence

from sqlalchemy import select, text

from services.api.app.memory.models import AsyncSessionLocal, ChatHistory


class ChatRepository:
    """Async repository for persisting and retrieving conversation turns.

    Uses SQLAlchemy async sessions backed by ``asyncpg``.  Each method
    opens its own session to keep transactions short-lived.
    """

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        user_id: str,
    ) -> None:
        """Persist a single chat turn to the database.

        Args:
            session_id: UUID string for the conversation thread.
            role: Speaker role -- ``"user"`` or ``"assistant"``.
            content: The message text to store.
            user_id: Authenticated user identifier for multi-tenancy.

        Raises:
            sqlalchemy.exc.SQLAlchemyError: On database write failure.
        """
        async with AsyncSessionLocal() as session:
            async with session.begin():
                msg = ChatHistory(
                    session_id=session_id,
                    role=role,
                    content=content,
                    user_id=user_id,
                )
                session.add(msg)
                # ``session.begin()`` commits automatically on exit

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

        Example:
            >>> history = await chat_repository.get_history(
            ...     "session-abc", limit=6
            ... )
            >>> messages = [
            ...     {"role": m.role, "content": m.content}
            ...     for m in history
            ... ]
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ChatHistory)
                .where(ChatHistory.session_id == session_id)
                .order_by(ChatHistory.created_at.desc())
                .limit(limit)
            )
            # Reverse to restore chronological (oldest -> newest) order
            rows = result.scalars().all()
            return list(reversed(rows))

    async def get_user_sessions(self, user_id: str, limit: int = 50) -> list[dict]:
        """Return sessions for a user, newest-first.

        Each dict contains:
            session_id, started_at, last_activity, message_count, preview.

        ``preview`` is the content of the first user message, truncated to
        120 characters.
        """
        sql = text("""
            WITH first_user_msg AS (
                SELECT
                    session_id,
                    content,
                    ROW_NUMBER() OVER (
                        PARTITION BY session_id ORDER BY created_at ASC
                    ) AS rn
                FROM chat_history
                WHERE user_id = :user_id AND role = 'user'
            )
            SELECT
                ch.session_id,
                MIN(ch.created_at)  AS started_at,
                MAX(ch.created_at)  AS last_activity,
                COUNT(*)            AS message_count,
                MAX(fum.content)    AS preview
            FROM chat_history ch
            LEFT JOIN first_user_msg fum
                ON fum.session_id = ch.session_id AND fum.rn = 1
            WHERE ch.user_id = :user_id
            GROUP BY ch.session_id
            ORDER BY MAX(ch.created_at) DESC
            LIMIT :limit
        """)
        async with AsyncSessionLocal() as session:
            result = await session.execute(sql, {"user_id": user_id, "limit": limit})
            rows = result.mappings().all()
            return [
                {
                    "session_id": r["session_id"],
                    "started_at": r["started_at"].isoformat()
                    if r["started_at"]
                    else None,
                    "last_activity": r["last_activity"].isoformat()
                    if r["last_activity"]
                    else None,
                    "message_count": r["message_count"],
                    "preview": (r["preview"] or "")[:120],
                }
                for r in rows
            ]

    async def get_session_messages(self, session_id: str, user_id: str) -> list[dict]:
        """Return all messages for a session in chronological order.

        Validates ownership: returns [] if the session belongs to a different user.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ChatHistory)
                .where(
                    ChatHistory.session_id == session_id,
                    ChatHistory.user_id == user_id,
                )
                .order_by(ChatHistory.created_at.asc())
            )
            rows = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "role": r.role,
                    "content": r.content,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]


# Global singleton -- stateless; no lifecycle management required
chat_repository = ChatRepository()
