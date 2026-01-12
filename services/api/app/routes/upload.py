# services/api/app/routes/upload.py
import boto3
import uuid
from fastapi import APIRouter, Depends
from services.api.app.config import settings
from services.api.app.auth.jwt import get_current_user

router = APIRouter()

s3_client = boto3.client("s3", region_name=settings.AWS_REGION)

@router.post("/generate-presigned-url")
async def generate_upload_url(filename: str, content_type: str, user: dict = Depends(get_current_user)):
    """Generates a secure S3 URL for direct frontend upload."""

    file_id = str(uuid.uuid4())
    s3_key = f"uploads/{user['id']}/{file_id}"

    url = s3_client.generate_presigned_url(
        ClientMethod='put_object',
        Params={'Bucket': settings.S3_BUCKET_NAME, 'Key': s3_key, 'ContentType': content_type},
        ExpiresIn=3600
    )

    return {"upload_url": url, "file_id": file_id, "s3_key": s3_key}