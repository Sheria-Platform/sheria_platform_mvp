# services/api/app/auth/permissions.py
"""Role-based permission matrix for Sheria Platform API endpoints.

Usage::

    from services.api.app.auth.permissions import require_role

    @router.post("/predict")
    async def predict(user: dict = Depends(require_role("judge", "magistrate"))):
        ...
"""

from fastapi import Depends, HTTPException, status

from services.api.app.auth.jwt import get_current_user

ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "judge":      frozenset({"chat", "legal_research", "upload", "predict", "verify", "history", "profile"}),
    "magistrate": frozenset({"chat", "legal_research", "upload", "predict", "verify", "history", "profile"}),
    "registrar":  frozenset({"chat", "upload", "verify", "history", "profile"}),
    "clerk":      frozenset({"chat", "upload", "history", "profile"}),
    "admin":      frozenset({"*"}),
}


def require_role(*allowed_roles: str):
    """Return a FastAPI dependency that enforces role-based access control.

    Admin users always pass regardless of ``allowed_roles``.

    Args:
        *allowed_roles: Roles that are permitted to access the endpoint
            (e.g. ``"judge"``, ``"magistrate"``).

    Returns:
        An async FastAPI dependency function that returns the user dict on
        success or raises ``HTTP 403`` if the user's role is not in
        ``allowed_roles``.

    Example::

        @router.post("/legal-research")
        async def legal_research(user: dict = Depends(require_role("judge", "magistrate"))):
            ...
    """

    async def _check(user: dict = Depends(get_current_user)) -> dict:
        role = user.get("role", "")
        if role == "admin":
            return user
        if role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' is not permitted to access this resource.",
            )
        return user

    return _check
