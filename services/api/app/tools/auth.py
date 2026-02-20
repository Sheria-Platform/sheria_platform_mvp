# services/api/app/auth/jwt.py
import time

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.requests import Request

from services.api.app.core.config import settings


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


