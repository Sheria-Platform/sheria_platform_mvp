"""Shared fixtures for Sheria API integration tests."""

import os
from datetime import datetime, timedelta
from unittest.mock import patch

# Set required env vars before any settings-dependent imports
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
os.environ.setdefault("NEO4J_PASSWORD", "test_password")
os.environ.setdefault("JWT_SECRET_KEY", "test_secret_key_for_unit_tests_only_not_real")

import pytest
from fastapi import FastAPI
from jose import jwt


@pytest.fixture(autouse=True)
def disable_rate_limiting():
    """Disable the global slowapi limiter so Redis state doesn't bleed between test runs."""
    from services.api.app.limiter import limiter as global_limiter

    with patch.object(global_limiter, "enabled", False):
        yield

_TEST_SECRET = "test_secret_key_for_unit_tests_only_not_real"
_TEST_ALGORITHM = "HS256"


def make_token(
    user_id: str = "user-001",
    role: str = "registrar",
    jti: str = "test-jti",
) -> str:
    """Generate a signed test JWT."""
    payload = {
        "sub": user_id,
        "role": role,
        "jti": jti,
        "exp": datetime.utcnow() + timedelta(hours=8),
    }
    return jwt.encode(payload, _TEST_SECRET, algorithm=_TEST_ALGORITHM)


def make_admin_token(user_id: str = "admin-001", jti: str = "admin-jti") -> str:
    return make_token(user_id=user_id, role="admin", jti=jti)


def build_app(router, prefix: str = "") -> FastAPI:
    """Minimal FastAPI app with a single router — no lifespan, no DB connections."""
    app = FastAPI()
    app.include_router(router, prefix=prefix)
    return app
