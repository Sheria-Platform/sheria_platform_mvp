# services/api/app/config.py
from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    Application Configuration.
    Reads environment variables automatically (case-insensitive).
    """

    # ------------------------------------------------------------------ #
    # General                                                               #
    # ------------------------------------------------------------------ #
    ENV: str = "prod"
    LOG_LEVEL: str = "INFO"

    # ------------------------------------------------------------------ #
    # Database                                                              #
    # ------------------------------------------------------------------ #
    DATABASE_URL: str  # required — e.g. postgresql+asyncpg://...
    ALLOWED_ORIGINS: str

    # ------------------------------------------------------------------ #
    # Redis                                                                 #
    # ------------------------------------------------------------------ #
    REDIS_URL: str  # required — e.g. redis://localhost:6379/0

    # ------------------------------------------------------------------ #
    # Qdrant (Vector Database)                                              #
    # ------------------------------------------------------------------ #
    QDRANT_HOST: str = "qdrant-service"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION: str = "kenya_law_reports"

    # ------------------------------------------------------------------ #
    # Neo4j (Graph Database)                                                #
    # ------------------------------------------------------------------ #
    NEO4J_URI: str = "bolt://neo4j-cluster:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str  # required — sensitive

    # ------------------------------------------------------------------ #
    # AWS S3                                                                #
    # ------------------------------------------------------------------ #
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str
    S3_ENDPOINT_URL: str
    AWS_ACCESS_KEY_ID: str
    AWS_SECRET_ACCESS_KEY: str

    # ------------------------------------------------------------------ #
    # Ollama (LLM & Embeddings)                                             #
    # ------------------------------------------------------------------ #
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_LLM_MODEL: str = "llama3.3"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"
    OLLAMA_TIMEOUT: int = 60  # seconds

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
