# services/api/app/limiter.py
"""slowapi rate-limiter singleton — shared across all routes."""
from slowapi import Limiter
from slowapi.util import get_remote_address

from services.api.app.config import settings

limiter = Limiter(key_func=get_remote_address, storage_uri=settings.REDIS_URL)
