"""Async token-bucket rate limiter with per-domain registry."""

import asyncio
import time
from typing import Dict


class AsyncRateLimiter:
    """Token-bucket limiter that allows at most `rps` requests per second."""

    def __init__(self, rps: float) -> None:
        if rps <= 0:
            raise ValueError("rps must be positive")
        self.interval = 1.0 / rps
        self._last_call: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Block until enough time has passed since the last call."""
        async with self._lock:
            now = time.monotonic()
            wait = self.interval - (now - self._last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()

    async def __aenter__(self) -> "AsyncRateLimiter":
        await self.acquire()
        return self

    async def __aexit__(self, *_) -> None:
        pass


class RateLimiterRegistry:
    """Singleton registry of per-domain rate limiters."""

    _limiters: Dict[str, AsyncRateLimiter] = {}

    @classmethod
    def get(cls, domain: str, rps: float) -> AsyncRateLimiter:
        if domain not in cls._limiters:
            cls._limiters[domain] = AsyncRateLimiter(rps)
        return cls._limiters[domain]

    @classmethod
    def clear(cls) -> None:
        cls._limiters.clear()
