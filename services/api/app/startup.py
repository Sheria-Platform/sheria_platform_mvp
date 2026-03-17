# services/api/app/startup.py
"""Application startup helpers for the Sheria Platform API.

These functions are called once during the FastAPI lifespan startup phase
(see ``services/api/main.py``).  Each function has a single, named
responsibility and is safe to call on every restart (all operations are
idempotent).
"""

import logging

import sqlalchemy
from qdrant_client.http.models import Distance, VectorParams

from services.api.app.clients.qdrant import qdrant_client
from services.api.app.config import settings
from services.api.app.memory.models import Base, engine
from services.api.app.memory.user_repository import user_repository

logger = logging.getLogger(__name__)

_EMBEDDING_DIM: int = settings.EMBEDDING_DIM


async def create_db_tables() -> None:
    """Create all database tables and apply lightweight column migrations.

    Runs ``CREATE TABLE IF NOT EXISTS`` for every SQLAlchemy ORM model
    registered under ``Base``.  Safe to call on every startup -- existing
    tables are left untouched.

    Also applies idempotent ``ALTER TABLE ... ADD COLUMN IF NOT EXISTS``
    statements for columns added after the initial schema was deployed.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Phase 3 addition: activation token TTL columns
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                "activation_token_expires_at TIMESTAMP WITHOUT TIME ZONE"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
                "approved_by VARCHAR"
            )
        )
        # Profile fields added in user-profile feature
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS avatar_url TEXT"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS bio TEXT"
            )
        )
        await conn.execute(
            sqlalchemy.text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS phone VARCHAR(30)"
            )
        )


async def ensure_qdrant_collections() -> None:
    """Create required Qdrant collections if they do not already exist.

    Collections created:
    - ``semantic_cache`` -- Q&A embedding pairs for semantic deduplication
      (cosine distance, threshold 0.95 in cache/semantic.py).

    Also validates the ``kenya_law_reports`` collection dimension against
    ``EMBEDDING_DIM`` and logs an error on mismatch so operators are alerted
    before vector searches silently return wrong results.

    Safe to call on every startup; existing collections are left untouched.
    """
    existing = {
        c.name for c in (await qdrant_client.client.get_collections()).collections
    }

    if "semantic_cache" not in existing:
        await qdrant_client.client.create_collection(
            collection_name="semantic_cache",
            vectors_config=VectorParams(
                size=_EMBEDDING_DIM,
                distance=Distance.COSINE,
            ),
        )
        logger.info("Created Qdrant collection: semantic_cache")

    if "kenya_law_reports" in existing:
        info = await qdrant_client.client.get_collection("kenya_law_reports")
        actual_dim = info.config.params.vectors.size
        if actual_dim != _EMBEDDING_DIM:
            logger.error(
                "DIMENSION MISMATCH: kenya_law_reports has %d dims but "
                "EMBEDDING_DIM=%d. Vector searches will fail. "
                "Drop and recreate the collection with the correct dimension.",
                actual_dim,
                _EMBEDDING_DIM,
            )
        else:
            logger.info("kenya_law_reports dimension validated: %d", actual_dim)


async def seed_admin() -> None:
    """Create the default admin account on first boot if none exists.

    Credentials are read from ``ADMIN_*`` environment variables so they
    can be rotated without code changes.  The seed is skipped when any
    admin already exists, making it safe to call on every startup.
    """
    import bcrypt  # use bcrypt directly -- passlib 1.7.4 is incompatible with bcrypt>=4

    hashed = bcrypt.hashpw(
        settings.ADMIN_PASSWORD.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")

    created = await user_repository.seed_admin(
        username=settings.ADMIN_USERNAME,
        email=settings.ADMIN_EMAIL,
        full_name=settings.ADMIN_FULL_NAME,
        hashed_password=hashed,
    )
    if created:
        logger.info(
            "Default admin account created",
            extra={"username": settings.ADMIN_USERNAME},
        )
    else:
        logger.info("Admin account already exists -- skipping seed")
