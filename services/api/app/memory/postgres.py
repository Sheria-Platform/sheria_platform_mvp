# services/api/app/memory/postgres.py

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text, func
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from services.api.app.config import settings
from services.api.app.memory import Base


# 2. Define the Chat History Table
class ChatHistory(Base):
    """
    Stores every conversation turn.
    """

    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, index=True)  # User's conversation ID
    user_id = Column(String, index=True)
    role = Column(String)  # "user" or "assistant"
    content = Column(Text)  # The text message
    metadata_ = Column(JSON, default={})  # Extra info (latency, tokens used)
    created_at = Column(DateTime, default=datetime.utcnow)


# 3. Async Engine & Session
engine = create_async_engine(settings.DATABASE_URL, echo=False)
asyncSessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False
)


class PostgresMemory:
    """
    Manager for persisting conversation state.
    """

    @staticmethod
    async def add_message(session_id: str, role: str, content: str, user_id: str):
        async with asyncSessionLocal() as session:
            async with session.begin():
                msg = ChatHistory(
                    session_id=session_id,
                    role=role,
                    content=content,
                    user_id=user_id,
                )
                session.add(msg)
                # Commit happens automatically via 'async with session.begin()'

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
            # Reverse to get chronological order (Oldest -> Newest)
            return result.scalars().all()[::-1]


postgres_memory = PostgresMemory()
