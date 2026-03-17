"""Integration tests for the auth flow — register → approve → activate → login → revoke."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from tests.integration.conftest import build_app, make_admin_token, make_token

# ── Test app factory ──────────────────────────────────────────────────────────


def _auth_app():
    from services.api.app.routes.auth import router

    app = build_app(router)

    # Wire slowapi in-memory limiter (no Redis) so rate-limiting tests don't need Redis
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.errors import RateLimitExceeded
    from slowapi.util import get_remote_address

    app.state.limiter = Limiter(key_func=get_remote_address)
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    return app


# ── JWT / blacklist patch context ─────────────────────────────────────────────


def _jwt_ctx():
    """Patch jwt.settings so test tokens validate correctly."""
    return patch("services.api.app.auth.jwt.settings", **{
        "JWT_SECRET_KEY": "test_secret_key_for_unit_tests_only_not_real",
        "JWT_ALGORITHM": "HS256",
    })


# ── Tests ─────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_register_creates_pending_user():
    """POST /register returns 201 and a confirmation message."""
    app = _auth_app()

    with patch("services.api.app.routes.auth.postgres_memory") as mock_mem:
        mock_mem.get_user_by_username = AsyncMock(return_value=None)
        mock_mem.get_user_by_email = AsyncMock(return_value=None)
        mock_mem.create_user = AsyncMock()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/register", json={
                "username": "jkamau",
                "email": "jkamau@judiciary.go.ke",
                "full_name": "James Kamau",
                "court_station": "Nairobi",
                "role": "registrar",
            })

    assert resp.status_code == 201
    assert "review" in resp.json()["message"].lower() or "submitted" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_login_blocked_for_pending_user():
    """POST /login with pending account returns 403."""
    app = _auth_app()

    pending_user = {
        "id": "u1",
        "username": "jkamau",
        "status": "pending",
        "hashed_password": None,
        "role": "registrar",
        "court_station": "Nairobi",
        "full_name": "James Kamau",
    }

    with patch("services.api.app.routes.auth.postgres_memory") as mock_mem:
        mock_mem.get_user_by_username = AsyncMock(return_value=pending_user)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/login", json={"username": "jkamau", "password": "pass"})

    assert resp.status_code == 403
    assert "pending" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_approve_user_returns_activation_token():
    """POST /approve/{id} by admin returns activation token and link."""
    app = _auth_app()
    admin_token = make_admin_token()

    approved_user = {
        "id": "u1",
        "username": "jkamau",
        "email": "jkamau@judiciary.go.ke",
        "full_name": "James Kamau",
        "status": "approved",
        "role": "registrar",
        "court_station": "Nairobi",
    }

    with (
        patch("services.api.app.routes.auth.postgres_memory") as mock_mem,
        patch(
            "services.api.app.auth.jwt.is_blacklisted",
            new=AsyncMock(return_value=False),
        ),
        patch("services.api.app.auth.jwt.settings") as mock_jwt,
        patch("services.api.app.routes.auth.send_activation_email", new=AsyncMock()),
    ):
        mock_jwt.JWT_SECRET_KEY = "test_secret_key_for_unit_tests_only_not_real"
        mock_jwt.JWT_ALGORITHM = "HS256"
        mock_mem.approve_user = AsyncMock()
        mock_mem.get_user_by_id = AsyncMock(return_value=approved_user)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                "/approve/u1",
                headers={"Authorization": f"Bearer {admin_token}"},
                json={"role": "registrar"},
            )

    assert resp.status_code == 200
    body = resp.json()
    assert "activation_token" in body
    assert len(body["activation_token"]) > 10


@pytest.mark.asyncio
async def test_activate_mismatched_passwords_returns_400():
    """POST /activate with mismatched passwords must return 400."""
    app = _auth_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/activate", json={
            "token": "some-token",
            "password": "Password1!",
            "confirm_password": "Different1!",
        })

    assert resp.status_code == 400
    assert "match" in resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_activate_sets_password():
    """POST /activate with valid token activates the account."""
    app = _auth_app()

    user = {"id": "u1", "status": "approved"}

    with patch("services.api.app.routes.auth.postgres_memory") as mock_mem:
        mock_mem.get_user_by_activation_token = AsyncMock(return_value=user)
        mock_mem.activate_user = AsyncMock()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/activate", json={
                "token": "valid-activation-token",
                "password": "SecurePass1!",
                "confirm_password": "SecurePass1!",
            })

    assert resp.status_code == 200
    assert "activated" in resp.json()["message"].lower()
    mock_mem.activate_user.assert_called_once()


@pytest.mark.asyncio
async def test_login_after_activation_returns_jwt():
    """POST /login with active account returns access_token."""
    import bcrypt

    app = _auth_app()
    hashed = bcrypt.hashpw(b"SecurePass1!", bcrypt.gensalt()).decode()

    active_user = {
        "id": "u1",
        "username": "jkamau",
        "status": "active",
        "hashed_password": hashed,
        "role": "registrar",
        "court_station": "Nairobi",
        "full_name": "James Kamau",
    }

    with (
        patch("services.api.app.routes.auth.postgres_memory") as mock_mem,
        patch("services.api.app.routes.auth.settings") as mock_settings,
        patch("services.api.app.routes.auth.store_user_jti", new=AsyncMock()),
    ):
        mock_settings.JWT_SECRET_KEY = "test_secret_key_for_unit_tests_only_not_real"
        mock_settings.JWT_ALGORITHM = "HS256"
        mock_mem.get_user_by_username = AsyncMock(return_value=active_user)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/login", json={
                "username": "jkamau",
                "password": "SecurePass1!",
            })

    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" in body
    assert body["user"]["role"] == "registrar"


@pytest.mark.asyncio
async def test_blacklisted_token_returns_401():
    """A request with a revoked JTI must be rejected with 401."""
    from services.api.app.routes.verify import router as verify_router

    # verify router has POST "" so we must mount it under a prefix
    app = build_app(verify_router, prefix="/verify")
    token = make_token(jti="revoked-jti")

    with (
        patch(
            "services.api.app.auth.jwt.is_blacklisted",
            new=AsyncMock(return_value=True),  # token revoked
        ),
        patch("services.api.app.auth.jwt.settings") as mock_settings,
    ):
        mock_settings.JWT_SECRET_KEY = "test_secret_key_for_unit_tests_only_not_real"
        mock_settings.JWT_ALGORITHM = "HS256"

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.get(
                "/verify/history",
                headers={"Authorization": f"Bearer {token}"},
            )

    assert resp.status_code == 401
    assert "revoked" in resp.json()["detail"].lower()
