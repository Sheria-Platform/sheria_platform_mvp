# services/api/app/auth/jwt.py
"""JWT authentication dependency for FastAPI routes.

Validates the ``Authorization: Bearer <token>`` header on every
protected endpoint.  The token is decoded using the application secret
and the configured algorithm; the decoded payload is returned as a
plain dict so routes can access ``user["id"]`` and ``user["role"]``.

Example:
    >>> @router.get("/protected")
    ... async def protected(user: dict = Depends(get_current_user)):
    ...     return {"user_id": user["id"]}
"""

import time
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

from services.api.app.config import settings

# Tells Swagger UI which URL issues tokens (informational only)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")


async def get_current_user(
    token: str = Depends(oauth2_scheme),
) -> dict[str, Any]:
    """FastAPI dependency that validates a JWT and returns the user dict.

    Decodes the token, verifies the signature and expiry, and extracts
    the user context from the JWT payload.

    Args:
        token: Raw JWT string extracted from the
            ``Authorization: Bearer`` header by FastAPI.

    Returns:
        A dictionary with keys:
            - ``"id"`` (str): The subject claim (``sub``).
            - ``"role"`` (str): User role, defaulting to ``"user"``.
            - ``"permissions"`` (list): Optional list of permission
              strings.

    Raises:
        HTTPException(401): If the token is missing, malformed,
            expired, or has an invalid signature.

    Example:
        >>> user = await get_current_user(valid_jwt_string)
        >>> user["id"]
        'judge-001'
        >>> user["role"]
        'judge'
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload: dict[str, Any] = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )

        user_id: str | None = payload.get("sub")
        if user_id is None:
            raise credentials_exception

        # Double-check expiry (python-jose already does this,
        # but we guard explicitly for clarity)
        exp: int | None = payload.get("exp")
        if exp and time.time() > exp:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token expired",
            )

        return {
            "id": user_id,
            "role": payload.get("role", "user"),
            "permissions": payload.get("permissions", []),
        }

    except JWTError:
        raise credentials_exception from None


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """FastAPI dependency that additionally requires the ``admin`` role.

    Use this instead of ``get_current_user`` on admin-only endpoints.
    """
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required",
        )
    return user
