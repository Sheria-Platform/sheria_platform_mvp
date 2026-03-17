# services/api/app/routes/profile.py
"""User self-service profile endpoints.

Provides three endpoints for authenticated users to view, edit, and upload
a profile picture for their own account.

Routes:
    GET  /api/v1/auth/me         -- fetch own profile
    PATCH /api/v1/auth/me        -- update editable fields
    POST /api/v1/auth/me/avatar  -- upload profile picture to MinIO/S3
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import boto3
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from pydantic import BaseModel

from services.api.app.auth.jwt import get_current_user
from services.api.app.config import settings
from services.api.app.memory.user_repository import user_repository

router = APIRouter()

# ── S3 / MinIO client (same pattern as routes/upload.py) ─────────────────────
if settings.MINIO_SERVER_URL:
    _s3 = boto3.client(
        "s3",
        endpoint_url=settings.MINIO_SERVER_URL,
        aws_access_key_id=settings.MINIO_ROOT_USER,
        aws_secret_access_key=settings.MINIO_ROOT_PASSWORD,
        region_name="us-east-1",
    )
else:
    _s3 = boto3.client("s3", region_name=settings.AWS_REGION)

_PRESIGNED_URL_TTL = 3600  # 1 hour

# Reuse a small thread pool for sync boto3 I/O
_executor = ThreadPoolExecutor(max_workers=2)

_ALLOWED_AVATAR_TYPES = {"image/jpeg", "image/png", "image/webp"}
_EXT_MAP = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}

# Fields never returned to callers
_SENSITIVE_FIELDS = {"hashed_password", "activation_token"}


def _safe_profile(user_dict: dict, avatar_presigned_url: str | None) -> dict:
    """Return a copy of *user_dict* with sensitive fields stripped."""
    return {
        k: v for k, v in user_dict.items() if k not in _SENSITIVE_FIELDS
    } | {"avatar_presigned_url": avatar_presigned_url}


def _generate_presigned_get(s3_key: str) -> str:
    return _s3.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET_NAME, "Key": s3_key},
        ExpiresIn=_PRESIGNED_URL_TTL,
    )


# ── GET /api/v1/auth/me ───────────────────────────────────────────────────────


@router.get("/me", summary="Get own profile")
async def get_my_profile(
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Return the authenticated user's full profile.

    If the user has uploaded an avatar, includes a short-lived presigned
    GET URL so the browser can display the image without requiring public
    bucket access.

    Args:
        user: Injected by ``get_current_user``; contains at least ``id``.

    Returns:
        Profile dict with all non-sensitive fields plus
        ``avatar_presigned_url`` (``None`` if no avatar is set).

    Raises:
        HTTPException(404): User record not found (should never happen for
            a valid JWT, but handled defensively).
    """
    row = await user_repository.get_user_by_id(user["id"])
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    presigned: str | None = None
    if row.get("avatar_url") and settings.S3_BUCKET_NAME:
        try:
            loop = asyncio.get_event_loop()
            presigned = await loop.run_in_executor(
                _executor, _generate_presigned_get, row["avatar_url"]
            )
        except Exception:
            pass  # avatar URL generation failure is non-fatal

    return _safe_profile(row, presigned)


# ── PATCH /api/v1/auth/me ─────────────────────────────────────────────────────


class ProfileUpdateRequest(BaseModel):
    """Editable profile fields.  All are optional; omit to leave unchanged."""

    full_name: str | None = None
    staff_number: str | None = None
    bio: str | None = None
    phone: str | None = None


@router.patch("/me", summary="Update own profile")
async def update_my_profile(
    body: ProfileUpdateRequest,
    user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """Update editable profile fields for the authenticated user.

    Only fields present in the request body are written to the database;
    omitted fields are not changed.

    Args:
        body: Partial profile update.
        user: Injected authenticated user.

    Returns:
        Updated profile dict (same shape as ``GET /me``).

    Raises:
        HTTPException(422): A provided string field is empty.
        HTTPException(404): User record not found.
    """
    # Validate non-empty strings
    for field, value in body.model_dump(exclude_none=True).items():
        if isinstance(value, str) and not value.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Field '{field}' must not be empty.",
            )

    await user_repository.update_profile(
        user_id=user["id"],
        full_name=body.full_name,
        staff_number=body.staff_number,
        bio=body.bio,
        phone=body.phone,
    )

    row = await user_repository.get_user_by_id(user["id"])
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    presigned: str | None = None
    if row.get("avatar_url") and settings.S3_BUCKET_NAME:
        try:
            loop = asyncio.get_event_loop()
            presigned = await loop.run_in_executor(
                _executor, _generate_presigned_get, row["avatar_url"]
            )
        except Exception:
            pass

    return _safe_profile(row, presigned)


# ── POST /api/v1/auth/me/avatar ───────────────────────────────────────────────


@router.post("/me/avatar", summary="Upload profile avatar")
async def upload_avatar(
    file: UploadFile,
    user: dict = Depends(get_current_user),
) -> dict[str, str | None]:
    """Upload a profile picture and store it in MinIO/S3.

    Validates content type (JPEG, PNG, or WebP) and file size (≤
    ``MAX_AVATAR_UPLOAD_MB`` MB).  The image is stored under key
    ``avatars/{user_id}.{ext}`` and a presigned GET URL is returned so
    the browser can display the new avatar immediately.

    Args:
        file: Uploaded image file.
        user: Injected authenticated user.

    Returns:
        ``{"avatar_presigned_url": "<url>"}``

    Raises:
        HTTPException(503): MinIO/S3 not configured.
        HTTPException(415): Unsupported media type.
        HTTPException(413): File exceeds size limit.
        HTTPException(500): Upload or presigning failure.
    """
    if not settings.S3_BUCKET_NAME:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Avatar storage is not configured. "
                "Set S3_BUCKET_NAME (and MINIO_SERVER_URL for local dev) in .env."
            ),
        )

    content_type = file.content_type or ""
    if content_type not in _ALLOWED_AVATAR_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type '{content_type}'. Allowed: JPEG, PNG, WebP.",
        )

    data = await file.read()
    max_bytes = settings.MAX_AVATAR_UPLOAD_MB * 1024 * 1024
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File exceeds the {settings.MAX_AVATAR_UPLOAD_MB} MB limit.",
        )

    ext = _EXT_MAP[content_type]
    s3_key = f"avatars/{user['id']}.{ext}"

    def _upload() -> None:
        import io
        _s3.upload_fileobj(
            io.BytesIO(data),
            settings.S3_BUCKET_NAME,
            s3_key,
            ExtraArgs={"ContentType": content_type},
        )

    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(_executor, _upload)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Upload failed: {exc}",
        ) from exc

    await user_repository.update_avatar(user["id"], s3_key)

    try:
        presigned = await loop.run_in_executor(
            _executor, _generate_presigned_get, s3_key
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Avatar uploaded but presigned URL generation failed: {exc}",
        ) from exc

    return {"avatar_presigned_url": presigned}
