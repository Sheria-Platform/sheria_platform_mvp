# services/api/app/routes/auth.py
"""User registration, login, and account activation endpoints.

Registration workflow:
    1. Staff submits POST /register  -> status=pending
    2. Admin reviews GET /pending -> approves via POST /approve/{id}
       -> status=approved, activation_token generated
    3. Staff uses token at POST /activate to set password -> status=active
    4. Staff logs in via POST /login -> receives JWT
"""

import asyncio
import uuid
from datetime import datetime, timedelta

import bcrypt as _bcrypt
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from jose import jwt
from pydantic import BaseModel

from services.api.app.auth.blacklist import blacklist_user_tokens, store_user_jti
from services.api.app.auth.jwt import require_admin
from services.api.app.auth.permissions import ROLE_PERMISSIONS
from services.api.app.config import settings
from services.api.app.limiter import limiter
from services.api.app.memory.audit_repository import audit_repository
from services.api.app.memory.user_repository import user_repository
from services.api.app.utils.email import send_activation_email

router = APIRouter()

_VALID_ROLES = {"judge", "magistrate", "registrar", "clerk", "admin"}
_REQUESTABLE_ROLES = _VALID_ROLES - {"admin"}


def _hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return _bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _create_token(user_id: str, username: str, role: str, court: str, jti: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=8)
    perms = sorted(ROLE_PERMISSIONS.get(role, frozenset()) - {"*"})
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "court": court,
        "jti": jti,
        "exp": expire,
        "permissions": perms,
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


# -- Request / Response models ------------------------------------------------


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


class ChangeRoleRequest(BaseModel):
    role: str


_SAFE_STATUS_TRANSITIONS: dict[str, set[str]] = {
    "active": {"suspended"},
    "suspended": {"active"},
}


# -- Endpoints -----------------------------------------------------------------


@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(req: RegisterRequest) -> dict:
    """Submit a registration request. Admin approval required before login."""
    if req.role not in _REQUESTABLE_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Choose from: {', '.join(sorted(_REQUESTABLE_ROLES))}",
        )
    existing_username, existing_email = await asyncio.gather(
        user_repository.get_user_by_username(req.username),
        user_repository.get_user_by_email(req.email),
    )
    if existing_username:
        raise HTTPException(status_code=400, detail="Username already taken")
    if existing_email:
        raise HTTPException(status_code=400, detail="Email already registered")

    await user_repository.create_user(
        username=req.username,
        email=req.email,
        full_name=req.full_name,
        court_station=req.court_station,
        role=req.role,
        staff_number=req.staff_number,
    )
    return {
        "message": "Registration request submitted. An administrator will review it."
    }


@router.post("/login")
@limiter.limit("5/15minutes")
async def login(request: Request, req: LoginRequest) -> dict:
    """Authenticate and receive a JWT. Account must be active."""
    user = await user_repository.get_user_by_username(req.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    status_map = {
        "pending": "Account pending administrator approval",
        "approved": "Account not yet activated. Use your activation link to set a password.",
        "suspended": "Account suspended. Contact your administrator.",
    }
    if user["status"] in status_map:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=status_map[user["status"]]
        )
    if user["status"] != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Account not active"
        )

    if not user.get("hashed_password") or not _verify_password(
        req.password, user["hashed_password"]
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )

    jti = str(uuid.uuid4())
    token = _create_token(
        user_id=user["id"],
        username=user["username"],
        role=user["role"],
        court=user["court_station"],
        jti=jti,
    )
    await store_user_jti(user["id"], jti)
    # Fire-and-forget: timestamp failure must never break login
    asyncio.create_task(user_repository.update_last_login(user["id"]))  # noqa: RUF006
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "role": user["role"],
            "court": user["court_station"],
            "full_name": user["full_name"],
            "token": token,
        },
    }


@router.post("/activate")
async def activate(req: ActivateRequest) -> dict:
    """Set password using an activation token sent by the administrator."""
    if req.password != req.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    if len(req.password) < 8:
        raise HTTPException(
            status_code=400, detail="Password must be at least 8 characters"
        )

    user = await user_repository.get_user_by_activation_token(req.token)
    if not user:
        raise HTTPException(
            status_code=404, detail="Invalid or expired activation token"
        )

    await user_repository.activate_user(user["id"], _hash_password(req.password))
    return {"message": "Account activated. You can now sign in."}


@router.get("/pending")
async def list_pending(admin: dict = Depends(require_admin)) -> list[dict]:
    """List all pending registration requests. Admin only."""
    users = await user_repository.get_pending_users()
    # Strip sensitive fields before returning
    return [
        {k: v for k, v in u.items() if k not in ("hashed_password", "activation_token")}
        for u in users
    ]


@router.post("/approve/{user_id}")
async def approve_user(
    user_id: str,
    req: ApproveRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    admin: dict = Depends(require_admin),
) -> dict:
    """Approve a pending user, assign their role, and email an activation link."""
    if req.role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")

    activation_token = str(uuid.uuid4())
    activation_link = f"/activate?token={activation_token}"

    await user_repository.approve_user(
        user_id=user_id,
        role=req.role,
        activation_token=activation_token,
        approved_by=admin["id"],
    )

    # Fire-and-forget: email failure never blocks or fails the HTTP response
    user = await user_repository.get_user_by_id(user_id)
    if user:
        asyncio.create_task(  # noqa: RUF006
            send_activation_email(
                to_address=user["email"],
                full_name=user["full_name"],
                activation_link=activation_link,
            )
        )

    ip = request.client.host if request.client else None
    background_tasks.add_task(
        audit_repository.log_action,
        admin_id=admin["id"],
        action="approve",
        target_user_id=user_id,
        detail={"role": req.role},
        ip_address=ip,
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
        status: Optional filter -- ``"pending"``, ``"approved"``,
            ``"active"``, or ``"suspended"``.  Omit to return all users.
    """
    users = await user_repository.get_users(status=status)
    return [
        {k: v for k, v in u.items() if k not in ("hashed_password", "activation_token")}
        for u in users
    ]


@router.post("/users/{user_id}/status")
async def update_user_status(
    user_id: str,
    req: UpdateStatusRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    admin: dict = Depends(require_admin),
) -> dict:
    """Suspend or reactivate a user account. Admin only.

    Valid transitions: ``active -> suspended``, ``suspended -> active``.
    All other target statuses or invalid transitions return 400.
    """
    if req.status not in ("active", "suspended"):
        raise HTTPException(
            status_code=400,
            detail="Invalid target status. Must be 'active' or 'suspended'.",
        )

    user = await user_repository.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    current = user["status"]
    if req.status not in _SAFE_STATUS_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot transition from '{current}' to '{req.status}'.",
        )

    await user_repository.update_user_status(user_id, req.status)
    if req.status == "suspended":
        await blacklist_user_tokens(user_id)

    ip = request.client.host if request.client else None
    action = "suspend" if req.status == "suspended" else "reactivate"
    background_tasks.add_task(
        audit_repository.log_action,
        admin_id=admin["id"],
        action=action,
        target_user_id=user_id,
        detail={"new_status": req.status},
        ip_address=ip,
    )

    return {
        "message": f"User status updated to '{req.status}'. "
        f"{'User can no longer log in.' if req.status == 'suspended' else 'User can now log in.'}"
    }


@router.post("/users/{user_id}/role")
async def change_user_role(
    user_id: str,
    req: ChangeRoleRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    admin: dict = Depends(require_admin),
) -> dict:
    """Change a user's role and immediately revoke their active token. Admin only.

    The target user must re-login to receive a new JWT reflecting the new role.

    Args:
        user_id: Primary-key UUID of the user whose role should change.
        req:     Body containing the new ``role`` string.
        admin:   Authenticated admin user from JWT.

    Returns:
        Confirmation message.

    Raises:
        HTTPException(400): If the role is invalid.
        HTTPException(404): If the user is not found.
    """
    if req.role not in _VALID_ROLES:
        raise HTTPException(status_code=400, detail="Invalid role")

    user = await user_repository.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    old_role = user["role"]
    if old_role == req.role:
        return {"message": f"User already has role '{req.role}'. No change made."}

    await user_repository.update_user_role(user_id, req.role)
    await blacklist_user_tokens(user_id)

    ip = request.client.host if request.client else None
    background_tasks.add_task(
        audit_repository.log_action,
        admin_id=admin["id"],
        action="role_change",
        target_user_id=user_id,
        detail={"old_role": old_role, "new_role": req.role},
        ip_address=ip,
    )

    return {
        "message": f"Role updated from '{old_role}' to '{req.role}'. User must re-login."
    }


@router.get("/audit-log")
async def get_audit_log(
    admin: dict = Depends(require_admin),
) -> list[dict]:
    """Return the most recent 200 admin audit log entries. Admin only."""
    return await audit_repository.get_recent_logs(limit=200)


@router.get("/analytics")
async def get_analytics(admin: dict = Depends(require_admin)) -> dict:
    """Return system-wide analytics across all judicial modules. Admin only."""
    from sqlalchemy import func, distinct, select

    from services.api.app.memory.models import (
        AdminAuditLog,
        AsyncSessionLocal,
        ChatHistory,
        IngestionJob,
        PredictionHistory,
        User,
        VerificationActivity,
    )

    # AsyncSession does not support concurrent operations on one session.
    # Run all queries sequentially within a single connection.
    async with AsyncSessionLocal() as session:
        user_status_rows = await session.execute(
            select(User.status, func.count(User.id).label("cnt")).group_by(User.status)
        )
        role_rows = await session.execute(
            select(User.role, func.count(User.id).label("cnt")).group_by(User.role)
        )
        court_rows = await session.execute(
            select(User.court_station, func.count(User.id).label("cnt"))
            .group_by(User.court_station)
            .order_by(func.count(User.id).desc())
            .limit(5)
        )
        recent_7d_result = await session.execute(
            select(func.count(User.id)).where(
                User.created_at >= datetime.utcnow() - timedelta(days=7)
            )
        )
        session_count_result = await session.execute(
            select(func.count(distinct(ChatHistory.session_id)))
        )
        verify_total_result = await session.execute(
            select(func.count(VerificationActivity.id))
        )
        authentic_count_result = await session.execute(
            select(func.count(VerificationActivity.id)).where(
                VerificationActivity.authentic == True  # noqa: E712
            )
        )
        avg_confidence_result = await session.execute(
            select(func.avg(VerificationActivity.confidence))
        )
        verify_type_rows = await session.execute(
            select(
                VerificationActivity.document_type,
                func.count(VerificationActivity.id).label("cnt"),
            ).group_by(VerificationActivity.document_type)
        )
        predict_total_result = await session.execute(
            select(func.count(PredictionHistory.id))
        )
        avg_months_result = await session.execute(
            select(
                func.avg(
                    (PredictionHistory.estimated_months_min + PredictionHistory.estimated_months_max) / 2.0
                )
            )
        )
        risk_rows = await session.execute(
            select(PredictionHistory.risk_level, func.count(PredictionHistory.id).label("cnt"))
            .where(PredictionHistory.risk_level.isnot(None))
            .group_by(PredictionHistory.risk_level)
        )
        top_court_rows = await session.execute(
            select(PredictionHistory.court, func.count(PredictionHistory.id).label("cnt"))
            .group_by(PredictionHistory.court)
            .order_by(func.count(PredictionHistory.id).desc())
            .limit(5)
        )
        ingest_count_result = await session.execute(
            select(func.count(IngestionJob.job_id))
        )
        audit_rows = await session.execute(
            select(
                AdminAuditLog.id,
                AdminAuditLog.action,
                AdminAuditLog.detail,
                AdminAuditLog.ip_address,
                AdminAuditLog.created_at,
                User.username.label("admin_username"),
            )
            .join(User, User.id == AdminAuditLog.admin_id, isouter=True)
            .order_by(AdminAuditLog.created_at.desc())
            .limit(20)
        )

    # ── Aggregate results ──────────────────────────────────────────────────
    status_counts: dict[str, int] = {}
    for row in user_status_rows.all():
        status_counts[row.status] = row.cnt

    total_users = sum(status_counts.values())
    active_users = status_counts.get("active", 0)
    pending_users = status_counts.get("pending", 0)
    suspended_users = status_counts.get("suspended", 0)

    users_by_role = {row.role: row.cnt for row in role_rows.all()}

    top_court_stations = [
        {"court_station": row.court_station, "count": row.cnt}
        for row in court_rows.all()
    ]

    recent_7d = recent_7d_result.scalar() or 0
    total_chat_sessions = session_count_result.scalar() or 0
    total_verifications = verify_total_result.scalar() or 0
    authentic_count = authentic_count_result.scalar() or 0
    raw_avg_confidence = avg_confidence_result.scalar()
    avg_confidence = float(raw_avg_confidence) if raw_avg_confidence is not None else 0.0

    by_document_type = {row.document_type: row.cnt for row in verify_type_rows.all()}
    fraudulent_count = total_verifications - authentic_count
    authenticity_rate = (
        round((authentic_count / total_verifications) * 100, 1)
        if total_verifications > 0
        else 0.0
    )

    total_predictions = predict_total_result.scalar() or 0
    raw_avg_months = avg_months_result.scalar()
    avg_estimated_months = (
        round(float(raw_avg_months), 1) if raw_avg_months is not None else 0.0
    )

    by_risk_level = {row.risk_level: row.cnt for row in risk_rows.all()}
    top_courts = [
        {"court": row.court, "count": row.cnt} for row in top_court_rows.all()
    ]
    total_ingestion_jobs = ingest_count_result.scalar() or 0

    audit_log = [
        {
            "id": row.id,
            "action": row.action,
            "admin": row.admin_username or "unknown",
            "detail": row.detail,
            "ip_address": row.ip_address,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in audit_rows.all()
    ]

    return {
        "overview": {
            "total_users": total_users,
            "active_users": active_users,
            "pending_users": pending_users,
            "suspended_users": suspended_users,
            "total_chat_sessions": total_chat_sessions,
            "total_verifications": total_verifications,
            "total_predictions": total_predictions,
            "total_ingestion_jobs": total_ingestion_jobs,
        },
        "users_by_role": users_by_role,
        "top_court_stations": top_court_stations,
        "recent_registrations_7d": recent_7d,
        "verifications": {
            "total": total_verifications,
            "authentic_count": authentic_count,
            "fraudulent_count": fraudulent_count,
            "authenticity_rate": authenticity_rate,
            "avg_confidence": round(avg_confidence, 2),
            "by_document_type": by_document_type,
        },
        "predictions": {
            "total": total_predictions,
            "avg_estimated_months": avg_estimated_months,
            "by_risk_level": by_risk_level,
            "top_courts": top_courts,
        },
        "audit_log": audit_log,
    }
