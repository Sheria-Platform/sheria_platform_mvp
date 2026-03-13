# services/api/app/routes/auth.py
"""User registration, login, and account activation endpoints.

Registration workflow:
    1. Staff submits POST /register  → status=pending
    2. Admin reviews GET /pending → approves via POST /approve/{id}
       → status=approved, activation_token generated
    3. Staff uses token at POST /activate to set password → status=active
    4. Staff logs in via POST /login → receives JWT
"""

import asyncio
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from jose import jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from services.api.app.auth.jwt import get_current_user, require_admin
from services.api.app.config import settings
from services.api.app.memory.postgres import postgres_memory
from services.api.app.utils.email import send_activation_email

router = APIRouter()

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

_VALID_ROLES = {"judge", "magistrate", "registrar", "clerk", "admin"}
_REQUESTABLE_ROLES = _VALID_ROLES - {"admin"}


def _hash_password(password: str) -> str:
    return _pwd_context.hash(password)


def _verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def _create_token(user_id: str, username: str, role: str, court: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=8)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "court": court,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# ── Request / Response models ─────────────────────────────────────────────

class RegisterRequest(BaseModel):
    username: str
    email: str
    full_name: str
    court_station: str
    role: str
    staff_number: str | None = None


class LoginRequest(BaseModel):
    username: str
    password: str


class ActivateRequest(BaseModel):
    token: str
    password: str
    confirm_password: str


class ApproveRequest(BaseModel):
    role: str


class UpdateStatusRequest(BaseModel):
    status: str  # "active" or "suspended"


_SAFE_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "active":    {"suspended"},
    "suspended": {"active"},
}


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest) -> dict:
    """Submit a registration request. Admin approval required before login."""
    if req.role not in _REQUESTABLE_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Choose from: {', '.join(sorted(_REQUESTABLE_ROLES))}",
        )
    existing_username, existing_email = await asyncio.gather(
        postgres_memory.get_user_by_username(req.username),
        postgres_memory.get_user_by_email(req.email),
    )
    if existing_username:
        raise HTTPException(status_code=400, detail="Username already taken")
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already registered")

    await postgres_memory.create_user(
        username=req.username,
        email=req.email,
        full_name=req.full_name,
        court_station=req.court_station,
        role=req.role,
        staff_number=req.staff_number,
    )
    return {"message": "Registration request submitted. An administrator will review it."}


@router.post("/login")
async def login(req: LoginRequest) -> dict:
    """Authenticate and receive a JWT. Account must be active."""
    user = await postgres_memory.get_user_by_username(req.username)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    status_map = {
        "pending":   "Account pending administrator approval",
        "approved":  "Account not yet activated. Use your activation link to set a password.",
        "suspended": "Account suspended. Contact your administrator.",
    }
    if user["status"] in status_map:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=status_map[user["status"]])
    if user["status"] != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account not active")

    if not user.get("hashed_password") or not _verify_password(req.password, user["hashed_password"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = _create_token(
        user_id=user["id"],
        username=user["username"],
        role=user["role"],
        court=user["court_station"],
    )
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id":        user["id"],
            "username":  user["username"],
            "role":      user["role"],
            "court":     user["court_station"],
            "full_name": user["full_name"],
            "token":     token,
        },
    }


@router.post("/activate")
async def activate(req: ActivateRequest) -> dict:
    """Set password using an activation token sent by the administrator."""
    if req.password != req.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    if len(req.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user = await postgres_memory.get_user_by_activation_token(req.token)
    if not user:
        raise HTTPException(status_code=404, detail="Invalid or expired activation token")

    await postgres_memory.activate_user(user["id"], _hash_password(req.password))
    return {"message": "Account activated. You can now sign in."}


@router.get("/pending")
async def list_pending(admin: dict = Depends(require_admin)) -> list[dict]:
    """List all pending registration requests. Admin only."""
    users = await postgres_memory.get_pending_users()
    # Strip sensitive fields before returning
    return [
        {k: v for k, v in u.items() if k not in ("hashed_password", "activation_token")}
        for u in users
    ]


@router.post("/approve/{user_id}")
async def approve_user(
    user_id: str,
    req: ApproveRequest,
    admin: dict = Depends(require_admin),
) -> dict:
    """Approve a pending user, assign their role, and email an activation link."""
    if req.role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")

    activation_token = str(uuid.uuid4())
    activation_link = f"/activate?token={activation_token}"

    await postgres_memory.approve_user(
        user_id=user_id,
        role=req.role,
        activation_token=activation_token,
        approved_by=admin["id"],
    )

    # Fire-and-forget: email failure never blocks or fails the HTTP response
    user = await postgres_memory.get_user_by_id(user_id)
    if user:
        asyncio.create_task(
            send_activation_email(
                to_address=user["email"],
                full_name=user["full_name"],
                activation_link=activation_link,
            )
        )

    return {
        "message": "User approved. An activation link has been sent to the user's email.",
        "activation_token": activation_token,
        "activation_link": activation_link,
    }


@router.get("/users")
async def list_users(
    status: str | None = None,
    admin: dict = Depends(require_admin),
) -> list[dict]:
    """List all user accounts with an optional ``?status=`` filter. Admin only.

    Args:
        status: Optional filter — ``"pending"``, ``"approved"``,
            ``"active"``, or ``"suspended"``.  Omit to return all users.
    """
    users = await postgres_memory.get_users(status=status)
    return [
        {k: v for k, v in u.items() if k not in ("hashed_password", "activation_token")}
        for u in users
    ]


@router.post("/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    req: UpdateStatusRequest,
    admin: dict = Depends(require_admin),
) -> dict:
    """Suspend or reactivate a user account. Admin only.

    Valid transitions: ``active → suspended``, ``suspended → active``.
    All other target statuses or invalid transitions return 400.
    """
    if req.status not in ("active", "suspended"):
        raise HTTPException(
            status_code=400,
            detail="Invalid target status. Must be 'active' or 'suspended'.",
        )

    user = await postgres_memory.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    current = user["status"]
    if req.status not in _SAFE_STATUS_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from '{current}' to '{req.status}'.",
        )

    await postgres_memory.update_user_status(user_id, req.status)
    return {"message": f"User status updated to '{req.status}'. "
                       f"{'User can no longer log in.' if req.status == 'suspended' else 'User can now log in.'}"}
