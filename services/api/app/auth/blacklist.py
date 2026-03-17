# services/api/app/auth/blacklist.py
"""Redis-backed JWT blacklist for immediate token revocation.

When a user is suspended, their active token JTI is blacklisted
so subsequent requests with the old token return 401 immediately,
without waiting for natural JWT expiry (8 hours).

Key scheme:
    user_jti:{user_id}          -> current JTI (TTL = JWT lifetime)
    token_blacklist:{jti}       -> "1" (TTL = JWT lifetime)
"""

from services.api.app.cache.redis import redis_client
from services.api.app.config import settings

_JTI_PREFIX = "user_jti:"
_BLACKLIST_PREFIX = "token_blacklist:"


async def store_user_jti(user_id: str, jti: str) -> None:
    """Record the current active JTI for a user (overwrites previous)."""
    r = redis_client.get_client()
    await r.setex(f"{_JTI_PREFIX}{user_id}", settings.TOKEN_BLACKLIST_TTL_SECONDS, jti)


async def blacklist_user_tokens(user_id: str) -> None:
    """Blacklist the current active token for a user (call on suspend)."""
    r = redis_client.get_client()
    jti = await r.get(f"{_JTI_PREFIX}{user_id}")
    if jti:
        await r.setex(
            f"{_BLACKLIST_PREFIX}{jti}",
            settings.TOKEN_BLACKLIST_TTL_SECONDS,
            "1",
        )


async def is_blacklisted(jti: str) -> bool:
    """Return True if the given JTI has been revoked."""
    r = redis_client.get_client()
    return bool(await r.exists(f"{_BLACKLIST_PREFIX}{jti}"))
