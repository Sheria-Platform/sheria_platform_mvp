# services/api/app/cache/redis.py
"""Async Redis client singleton.

Provides a single shared ``redis.asyncio`` connection pool used by
the semantic cache and (optionally) rate-limiting middleware.

Example:
    >>> r = redis_client.get_client()
    >>> await r.set("key", "value", ex=3600)
    >>> value = await r.get("key")
"""

import logging

import redis.asyncio as aioredis

from services.api.app.config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Singleton async Redis connection pool.

    Uses ``redis.asyncio.from_url`` which creates a connection pool
    internally.  The pool is initialised in ``connect()`` and torn down
    in ``close()``, both called from the application lifespan context.

    Attributes:
        redis: The underlying async Redis client, or ``None`` before
            ``connect()`` is called.
    """

    def __init__(self) -> None:
        """Initialise with no active connection."""
        self.redis: aioredis.Redis | None = None

    async def connect(self) -> None:
        """Open the Redis connection pool.

        Idempotent — safe to call multiple times.

        Raises:
            redis.exceptions.ConnectionError: If Redis is unreachable.
        """
        if self.redis:
            return

        self.redis = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,  # return str, not bytes
        )
        logger.info("Redis client initialised. url=%s", settings.REDIS_URL)

    async def close(self) -> None:
        """Close the Redis connection pool.

        Safe to call even if ``connect()`` was never called.
        """
        if self.redis:
            await self.redis.close()
            logger.info("Redis client closed.")

    def get_client(self) -> aioredis.Redis:
        """Return the raw async Redis client.

        Returns:
            The ``redis.asyncio.Redis`` instance.

        Raises:
            RuntimeError: If called before ``connect()``.

        Example:
            >>> r = redis_client.get_client()
            >>> await r.ping()
            True
        """
        if not self.redis:
            raise RuntimeError("RedisClient not connected. Call connect() first.")
        return self.redis


# Global singleton — lifecycle managed by main.py lifespan
redis_client = RedisClient()
