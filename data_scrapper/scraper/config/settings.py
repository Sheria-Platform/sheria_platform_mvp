"""Pydantic-settings configuration loaded from environment variables."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # MinIO / S3-compatible storage
    minio_endpoint: str = Field(default="localhost:9000", alias="MINIO_ENDPOINT")
    minio_access_key: str = Field(default="minioadmin", alias="MINIO_ACCESS_KEY")
    minio_secret_key: str = Field(default="minioadmin", alias="MINIO_SECRET_KEY")
    minio_bucket: str = Field(default="legal-documents", alias="MINIO_BUCKET")
    minio_secure: bool = Field(default=False, alias="MINIO_SECURE")

    # PostgreSQL
    database_url: str = Field(
        default="postgresql://ragadmin:changeme@localhost:5432/rag_db",
        alias="DATABASE_URL",
    )

    # Scraper behaviour
    max_concurrent_downloads: int = Field(
        default=5, alias="MAX_CONCURRENT_DOWNLOADS"
    )
    default_rate_limit_rps: float = Field(
        default=0.5, alias="DEFAULT_RATE_LIMIT_RPS"
    )
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")


def get_settings() -> Settings:
    return Settings()
