# services/api/app/clients/qdrant.py
"""Async Qdrant vector database client.

Wraps ``qdrant_client.AsyncQdrantClient`` to provide a clean singleton
interface for the rest of the application.  Lifecycle is managed by the
FastAPI lifespan handler in ``services/api/main.py``.
"""

import logging

from qdrant_client import AsyncQdrantClient
from qdrant_client.http.models import ScoredPoint

from services.api.app.core.config import settings

logger = logging.getLogger(__name__)


class VectorDBClient:
    """Async wrapper for Qdrant vector database operations.

    Initialises a single ``AsyncQdrantClient`` with gRPC transport
    (faster for large payloads) and exposes a simplified ``search``
    interface over the configured collection.

    Attributes:
        client: The underlying ``AsyncQdrantClient`` instance.
    """

    def __init__(self) -> None:
        """Create the Qdrant client using settings from config."""
        self.client: AsyncQdrantClient = AsyncQdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            prefer_grpc=True,        # gRPC for lower latency
        )

    async def connect(self) -> None:
        """Verify the Qdrant connection at application startup.

        Fetches the collection list as a lightweight health check.

        Raises:
            Exception: If Qdrant is unreachable or returns an error.
        """
        try:
            collections = await self.client.get_collections()
            logger.info(
                "Qdrant connected. collections=%d",
                len(collections.collections),
            )
        except Exception as exc:
            logger.error("Qdrant connection failed: %s", exc)
            raise

    async def disconnect(self) -> None:
        """Close the Qdrant connection at application shutdown."""
        try:
            await self.client.close()
            logger.info("Qdrant client closed.")
        except Exception as exc:
            logger.warning("Error closing Qdrant client: %s", exc)

    async def search(
        self,
        vector: list[float],
        limit: int = 5,
    ) -> list[ScoredPoint]:
        """Perform an approximate nearest-neighbour search.

        Args:
            vector: The query embedding vector.  Must match the
                dimension of the indexed collection.
            limit: Maximum number of results to return.

        Returns:
            A list of ``ScoredPoint`` objects sorted by descending
            cosine similarity score.  Each point exposes
            ``.payload`` (document metadata) and ``.score``.

        Raises:
            qdrant_client.http.exceptions.UnexpectedResponse: On
                Qdrant API errors (e.g. collection not found).
        """
        response = await self.client.query_points(
            collection_name=settings.QDRANT_COLLECTION,
            query=vector,
            limit=limit,
            with_payload=True,
        )

        return response.points


# Global singleton — lifecycle managed by main.py lifespan
qdrant_client = VectorDBClient()
