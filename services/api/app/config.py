# services/api/app/config.py
"""Application configuration loaded from environment variables.

Uses pydantic-settings so every field can be overridden by an env var
of the same name (case-insensitive).  Copy ``.env.example`` to ``.env``
and fill in the required values before starting the service.

Example:
    >>> from services.api.app.config import settings
    >>> print(settings.OLLAMA_BASE_URL)
    http://ollama:11434
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Pydantic settings model for the Sheria API service.

    All fields map 1-to-1 to environment variables.  Required fields
    (those without defaults) **must** be provided via ``.env`` or the
    shell environment; the application will fail to start otherwise.

    Attributes:
        ENV: Runtime environment tag (``"dev"``, ``"staging"``,
            ``"prod"``).
        LOG_LEVEL: Python logging level string.
        DATABASE_URL: Async PostgreSQL DSN, e.g.
            ``postgresql+asyncpg://user:pass@host:5432/db``.
        REDIS_URL: Redis connection URL, e.g.
            ``redis://localhost:6379/0``.
        QDRANT_HOST: Hostname of the Qdrant vector database.
        QDRANT_PORT: REST port of the Qdrant server.
        QDRANT_COLLECTION: Name of the primary Qdrant collection.
        NEO4J_URI: Bolt URI for the Neo4j graph database.
        NEO4J_USER: Neo4j username.
        NEO4J_PASSWORD: Neo4j password (sensitive).
        AWS_REGION: AWS region for S3 presigned URLs.
        S3_BUCKET_NAME: S3 bucket for court document storage.
        OLLAMA_BASE_URL: Base URL of the Ollama HTTP server.
        OLLAMA_LLM_MODEL: Ollama model name for chat completion.
        OLLAMA_EMBEDDING_MODEL: Ollama model name for embeddings.
        OLLAMA_TIMEOUT: Seconds before an Ollama request times out.
        JWT_SECRET_KEY: Secret used to sign/verify JWT tokens
            (sensitive).
        JWT_ALGORITHM: JWT signing algorithm.
        OTEL_EXPORTER_OTLP_ENDPOINT: Optional OTLP collector URL for
            distributed tracing.
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
    S3_BUCKET_NAME: str = ""

    # ------------------------------------------------------------------ #
    # Ollama (LLM & Embeddings)                                             #
    # ------------------------------------------------------------------ #
    OLLAMA_BASE_URL: str = "http://ollama:11434"
    OLLAMA_LLM_MODEL: str = "llama3.3"
    OLLAMA_EMBEDDING_MODEL: str = "nomic-embed-text"
    OLLAMA_TIMEOUT: int = 60  # seconds

    # ------------------------------------------------------------------ #
    # Security                                                              #
    # ------------------------------------------------------------------ #
    JWT_SECRET_KEY: str  # required — sensitive
    JWT_ALGORITHM: str = "HS256"

    # ------------------------------------------------------------------ #
    # Observability                                                          #
    # ------------------------------------------------------------------ #
    OTEL_EXPORTER_OTLP_ENDPOINT: str | None = None

    class Config:
        """Pydantic configuration."""

        env_file = ".env"
        extra = "ignore"


settings: Settings = Settings()
