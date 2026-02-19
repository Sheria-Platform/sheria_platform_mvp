from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (AsyncSession, async_sessionmaker,
                                    create_async_engine)
from sqlalchemy.orm import DeclarativeBase

from services.api.app.core.config import settings


class Base(DeclarativeBase):
    """Base class for SQLAlchemy ORM Models."""


engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True
)

sessionLocal = async_sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
    class_=AsyncSession
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency function that provides a database session for FastAPI endpoints.

    This function creates and yields an async database session from the session pool.
    The session is automatically closed when the context exits, ensuring proper
    resource cleanup. Typically used as a FastAPI dependency injection.

    The function implements proper error handling by rolling back the session on
    exceptions and ensuring the session is always closed in the finally block.

    Args:

    Yields:
        AsyncSession: An async SQLAlchemy session instance for database operations.
            The session is configured with autocommit=False, autoflush=False, and
            expire_on_commit=False for optimal async performance.

    Raises:
        Exception: Re-raises any exception that occurs during database operations
            after performing a rollback on the session.

    Example:
        @app.get("/users")
        async def get_users(db: AsyncSession = Depends(get_db)):
            result = await db.execute(select(User))
            return result.scalars().all()
    """
    async with sessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
