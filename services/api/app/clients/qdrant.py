# services/api/app/clients/qdrant.py
from qdrant_client import AsyncQdrantClient

from services.api.app.config import settings


class VectorDBClient:
    """
    Async Client for Qdrant.
    """

    def __init__(self):
        self.client = AsyncQdrantClient(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            # In prod, we might enable gRPC for slightly faster performance
            prefer_grpc=True,
            # Skip version compatibility check to avoid warnings
            check_compatibility=False,
        )

    async def connect(self):
        """
        Test connection and initialize Qdrant client.
        """
        try:
            collections = await self.client.get_collections()
            print(
                f"✓ Qdrant connected successfully. Collections: {len(collections.collections)}"
            )
        except Exception as e:
            print(f"✗ Qdrant connection failed: {e}")
            raise

    async def disconnect(self):
        """
        Close Qdrant connection.
        """
        try:
            await self.client.close()
            print("✓ Qdrant client closed successfully")
        except Exception as e:
            print(f"✗ Error closing Qdrant client: {e}")

    async def search(self, vector: list[float], limit: int = 5):
        """
        Performs Semantic Search.
        """
        return await self.client.search(
            collection_name=settings.QDRANT_COLLECTION,
            query_vector=vector,
            limit=limit,
            with_payload=True,
        )


# Global instance
qdrant_client = VectorDBClient()
