import logging
import uuid

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from botocore.config import Config
from fastapi.responses import JSONResponse

from services.api.app.services.auth import get_current_user  # Assume auth exists
from services.api.app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Initialize S3 Client (boto3 is synchronous, but presigning is fast/CPU-bound)
s3_client = boto3.client(
    "s3",
    region_name=settings.AWS_REGION,
    aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
    aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
    endpoint_url=settings.S3_ENDPOINT_URL if settings.S3_ENDPOINT_URL else None,
    config=Config(
        s3={'addressing_style': 'path'},
        signature_version='s3v4'
    )
)


class PresignedURLRequest(BaseModel):
    filename: str
    content_type: str  # e.g., "application/pdf"


class PresignedURLResponse(BaseModel):
    upload_url: str
    file_id: str
    s3_key: str


@router.post("/generate-presigned-url", response_model=PresignedURLResponse)
async def generate_upload_url(
        req: PresignedURLRequest, user: dict = Depends(get_current_user)  # Secure endpoint
):
    """
    Generates a secure, temporary URL for the frontend to upload a file directly to S3.
    Use case: Handling 1GB+ PDF/Video files without blocking the API server.
    """
    # 1. Generate a unique file ID (UUID) to prevent overwrites
    file_id = str(uuid.uuid4())
    extension = req.filename.split(".")[-1] if "." in req.filename else "bin"
    s3_key = f"uploads/{user['sub']}/{file_id}.{extension}"

    try:
        url = s3_client.generate_presigned_url(
            ClientMethod="put_object",
            Params={
                "Bucket": settings.S3_BUCKET_NAME,
                "Key": s3_key,
                "ContentType": req.content_type,
                "Metadata": {"original_filename": req.filename, "user_id": user["id"]},
            },
            ExpiresIn=3600,
        )

        return PresignedURLResponse(upload_url=url, file_id=file_id, s3_key=s3_key)

    except Exception as e:
        logger.error(f"Error generating presigned URL: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/upload-file", response_model=PresignedURLResponse)
async def upload_file_to_minio(
        file: UploadFile = File(...),
        user: dict = Depends(get_current_user)
):
    """
    Endpoint to handle file uploads to S3.
    """
    file_id = str(uuid.uuid4())
    extension = file.filename.split(".")[-1] if "." in file.filename else "bin"
    s3_key = f"uploads/{user['sub']}/{file_id}.{extension}"

    try:
        transfer_config = TransferConfig(
            multipart_threshold=5 * 1024 * 1024,
            multipart_chunksize=5 * 1024 * 1024,
            max_concurrency=5,
            use_threads=True
        )

        extra_args = {
            "ContentType": file.content_type or "application/octet-stream",
            "Metadata": {
                "original_name": file.filename or "unknown"
            }
        }
        s3_client.upload_fileobj(
            Fileobj=file.file,
            Bucket=settings.S3_BUCKET_NAME,
            Key=s3_key,
            ExtraArgs=extra_args,
            Config=transfer_config
        )

        return JSONResponse({
            "message": "Upload successful",
            "s3_key": s3_key,
            "filename": file.filename
        })

    except ClientError as exc:
        logger.exception(
            f"MinIO upload failed: {exc}",
            extra={
                "bucket": settings.S3_BUCKET_NAME,
                "key": s3_key,
                "filename": file.filename
            }
        )
        raise
    except Exception as e:
        logger.error(f"MinIO upload error: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail=str(e))

    finally:
        file.file.close()
