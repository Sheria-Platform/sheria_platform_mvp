# services/api/app/auth/jwt.py
import time

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.requests import Request

from services.api.app.config import settings


def decode_token(request: Request):
    auth_headers = request.headers.get("Authorization")
    if not auth_headers:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authorization header not found")

    try:
        token = auth_headers.split(' ')[1]
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )
    return token


async def get_current_user(token: str = Depends(decode_token)) -> dict:
    """
    Validates the JWT Token from the Authorization header.
    Decodes user info (ID, Role, Permissions).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # 1. Decode Token
        # Verify signature using the Secret Key defined in Config
        payload = jwt.decode(
            token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
        )

        user_id: str = payload.get("sub")
        role: str = payload.get("role", "user")

        if user_id is None:
            raise credentials_exception

        # 2. Check Expiration (Redundant if jwt.decode does it, but good for safety)
        exp = payload.get("exp")
        if exp and time.time() > exp:
            raise HTTPException(status_code=401, detail="Token expired")
        # Return user context dict
        return {
            "id": user_id,
            "role": role,
            "permissions": payload.get("permissions", []),
        }

    except Exception:
        raise credentials_exception
