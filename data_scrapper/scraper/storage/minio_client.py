"""boto3 MinIO wrapper for S3-compatible document storage."""

import io
import json
import logging
from typing import Optional

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.exceptions import ClientError

from scraper.config.settings import Settings

logger = logging.getLogger(__name__)

# Multipart upload threshold: 25 MB (same as project's bulk_upload_s3.py)
_TRANSFER_CONFIG = TransferConfig(
    multipart_threshold=1024 * 25,
    max_concurrency=10,
    multipart_chunksize=1024 * 25,
    use_threads=True,
)


class MinIOClient:
    """Thin wrapper around boto3 S3 client configured for MinIO."""

    def __init__(self, settings: Settings) -> None:
        scheme = "https" if settings.minio_secure else "http"
        self._bucket = settings.minio_bucket
        self._client = boto3.client(
            "s3",
            endpoint_url=f"{scheme}://{settings.minio_endpoint}",
            aws_access_key_id=settings.minio_access_key,
            aws_secret_access_key=settings.minio_secret_key,
            # Disable AWS-specific signature checks for MinIO
            config=boto3.session.Config(signature_version="s3v4"),
        )

    # ------------------------------------------------------------------
    # Bucket management
    # ------------------------------------------------------------------

    def ensure_bucket(self, bucket: Optional[str] = None) -> None:
        """Create the bucket if it doesn't already exist."""
        bucket = bucket or self._bucket
        try:
            self._client.head_bucket(Bucket=bucket)
            logger.debug("Bucket '%s' already exists.", bucket)
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in ("404", "NoSuchBucket"):
                self._client.create_bucket(Bucket=bucket)
                logger.info("Created bucket '%s'.", bucket)
            else:
                raise

    # ------------------------------------------------------------------
    # Upload helpers
    # ------------------------------------------------------------------

    def upload_document(
        self,
        content: bytes,
        path: str,
        metadata: dict,
        content_type: str = "application/octet-stream",
        bucket: Optional[str] = None,
    ) -> None:
        """Upload raw bytes to MinIO with optional S3 object metadata."""
        bucket = bucket or self._bucket
        # S3 metadata values must be strings
        str_meta = {k: str(v) for k, v in metadata.items() if v is not None}
        self._client.upload_fileobj(
            io.BytesIO(content),
            bucket,
            path,
            ExtraArgs={"Metadata": str_meta, "ContentType": content_type},
            Config=_TRANSFER_CONFIG,
        )
        logger.info("Uploaded %d bytes → s3://%s/%s", len(content), bucket, path)

    def upload_metadata_json(
        self,
        meta_dict: dict,
        base_path: str,
        bucket: Optional[str] = None,
    ) -> None:
        """Store metadata as a companion JSON file at `{base_path}.meta.json`."""
        bucket = bucket or self._bucket
        json_path = f"{base_path}.meta.json"
        payload = json.dumps(meta_dict, indent=2).encode()
        self._client.put_object(
            Bucket=bucket,
            Key=json_path,
            Body=payload,
            ContentType="application/json",
        )
        logger.debug("Wrote metadata → s3://%s/%s", bucket, json_path)

    # ------------------------------------------------------------------
    # Existence check
    # ------------------------------------------------------------------

    def document_exists(self, path: str, bucket: Optional[str] = None) -> bool:
        """Return True if the object already exists (for duplicate detection)."""
        bucket = bucket or self._bucket
        try:
            self._client.head_object(Bucket=bucket, Key=path)
            return True
        except ClientError as exc:
            if exc.response["Error"]["Code"] in ("404", "NoSuchKey"):
                return False
            raise

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def get_bucket_stats(self, bucket: Optional[str] = None) -> dict:
        """Return total object count and cumulative size in bytes."""
        bucket = bucket or self._bucket
        paginator = self._client.get_paginator("list_objects_v2")
        count = 0
        total_bytes = 0
        for page in paginator.paginate(Bucket=bucket):
            for obj in page.get("Contents", []):
                count += 1
                total_bytes += obj.get("Size", 0)
        return {"bucket": bucket, "object_count": count, "total_bytes": total_bytes}
