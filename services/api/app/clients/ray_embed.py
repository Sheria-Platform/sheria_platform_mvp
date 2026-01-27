# services/api/app/clients/ray_embed.py
import logging

import httpx

from services.api.app.config import settings

logger = logging.getLogger(__name__)


class RayEmbedClient:
    """
    Client for the Ray Serve Embedding Service.
    Uses HTTPX for async non-blocking HTTP calls.
    """

    @staticmethod
    async def embed_query(text: str) -> list[float]:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                settings.RAY_EMBED_ENDPOINT,
                json={
                    "input": text,
                    "model": settings.RAY_EMBED_MODEL,
                },  # "query" instructs model to optimize for retrieval
            )
            data = response.json()

            if 'error' in data:
                logger.error(f"Error embedding text: {response.status_code}. Error: {data['error']}")

                return []

            return [item["embedding"] for item in data["data"]]

    @staticmethod
    async def embed_documents(texts: list[str]) -> list[list[float]]:
        """Used during ingestion"""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                settings.RAY_EMBED_ENDPOINT,
                json={
                    'input': texts,
                    "model": settings.RAY_EMBED_MODEL
                },
            )
            data = response.json()

            if 'error' in data:
                logger.error(f"Error embedding text: {response.status_code}. Error: {data['error']}")

                return []

            return [item["embedding"] for item in data["data"]]


embed_client = RayEmbedClient()
