# services/api/app/config.py
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application Configuration.
    Reads environment variables automatically (case-insensitive).
    """

    # General
    ENV: str = "prod"
    LOG_LEVEL: str = "INFO"

    ALLOWED_ORIGINS: str

    # Database (Aurora Postgres)
    DATABASE_URL: str  # e.g., postgresql+asyncpg://user:pass@host:5432/db

    # Redis (Cache)
    REDIS_URL: str  # e.g., redis://elasticache-endpoint:6379/0

    # Vector DB (Qdrant)
    QDRANT_HOST: str = "qdrant-service"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "rag_collection"

    # Graph DB (Neo4j)
    NEO4J_URI: str = "bolt://neo4j-cluster:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str  # Sensitive

    # AWS S3 (Documents)
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str
    S3_ENDPOINT_URL: str
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str

    # Ray Serve (Internal LLM/Embeddings)
    RAY_LLM_ENDPOINT: str = "http://llm-service:8000/llm"
    RAY_EMBED_ENDPOINT: str = "http://embed-service:8000/embed"

    RAY_CHAT_MODEL: str
    RAY_EMBED_MODEL: str

    # Security
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"

    # OpenTelemetry (Optional - for observability)
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

    @property
    def cors_origins(self) -> List[str]:
        """
        Parse and return the list of allowed CORS origins.

        This property converts the comma-separated ALLOWED_ORIGINS string into a list
        of individual origin URLs, with whitespace stripped from each entry.

        Returns:
            List[str]: A list of allowed CORS origin URLs.
        """
        return [origin.strip() for origin in self.ALLOWED_ORIGINS.split(",")]


# Instantiate singleton
settings = Settings()
