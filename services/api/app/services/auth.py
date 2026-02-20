from typing import Dict

import jwt
from fastapi import HTTPException, status
from fastapi.requests import Request

from services.api.app.core.config import settings


async def get_current_user(request: Request) -> Dict:
    """
    Extract and validate user details from the JWT token in the request's Authorization header.

    This function retrieves the JWT access token from the Authorization header,
    decodes it to extract user information, and validates that the token contains
    a valid user ID. It performs authentication checks to ensure the token is
    present, properly formatted, valid, and contains the required user information.

    Args:
        request (Request): The FastAPI request object containing the Authorization header
                          with the JWT token in the format "Bearer <token>".

    Returns:
        Dict: A dictionary containing the decoded token payload with user details,
              including the user ID in the "sub" field and any other claims present
              in the token.

    Raises:
        HTTPException: With status 401 (UNAUTHORIZED) if the Authorization header is missing,
                      improperly formatted, or if the token is invalid or expired.
        HTTPException: With status 403 (FORBIDDEN) if the token is valid but does not
                      contain a user ID in the "sub" field.
    """
    auth_header = request.headers.get("Authorization")

    if not auth_header or ' ' not in auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization token required"
        )

    try:
        token = auth_header.split(' ')[1]
        user_details = decode_token(token)
    except Exception as e:
        print(str(e))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    user_id = user_details.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User ID not found in token"
        )

    return user_details


def decode_token(token: str):
    try:
        if settings.DEBUG:
            payload = jwt.decode(
                jwt=token,
                key=None,
                algorithms=[settings.JWT_ALGORITHM],
                options={
                    'verify_signature': False
                }
            )
        else:
            payload = jwt.decode(
                jwt=token,
                key=settings.JWT_SECRET_KEY,
                algorithms=[settings.JWT_ALGORITHM]
            )

        return payload
    except jwt.ExpiredSignatureError:
        raise Exception("Token expired")
    except jwt.InvalidTokenError:
        raise Exception("Invalid token")
