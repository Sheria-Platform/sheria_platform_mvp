# services/api/app/memory/postgres.py
"""PostgreSQL-backed conversation memory.

Persists every chat turn (user and assistant messages) to the
``chat_history`` table so conversation context survives across API
restarts and can be audited.

Example:
    >>> await postgres_memory.add_message(
    ...     session_id="abc-123",
    ...     role="user",
    ...     content="What is adverse possession?",
    ...     user_id="judge-001",
    ... )
    >>> history = await postgres_memory.get_history("abc-123", limit=6)
"""

from datetime import datetime
from typing import Sequence

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from services.api.app.config import settings

Base = declarative_base()


class ChatHistory(Base):
    """ORM model for the ``chat_history`` table.

    Each row represents one turn in a conversation.

    Attributes:
        id: Auto-incrementing primary key.
        session_id: UUID string grouping messages into a conversation.
        user_id: Identifier of the authenticated user.
        role: Speaker -- ``"user"``, ``"assistant"``, or ``"system"``.
        content: The raw message text.
        metadata_: Flexible JSON blob for token counts, latency, etc.
        created_at: UTC timestamp of insertion.
    """

    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    role = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    metadata_ = Column(JSON, default={}, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


# Async engine -- ``echo=False`` suppresses SQL statement logging
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionLocal: sessionmaker = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class PostgresMemory:
    """Async manager for persisting and retrieving conversation turns.

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
            >>> history = await postgres_memory.get_history(
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
                    "started_at": r["started_at"].isoformat() if r["started_at"] else None,
                    "last_activity": r["last_activity"].isoformat() if r["last_activity"] else None,
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
postgres_memory = PostgresMemory()
