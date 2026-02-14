# pipelines/ingestion/indexing/qdrant.py
import os
import uuid
from typing import Any

from qdrant_client import QdrantClient
from qdrant_client.http import models


class QdrantIndexer:
    """
    Writes vectors to Qdrant.
    """

    def __init__(self):
        host = os.getenv("QDRANT_HOST", "localhost")
        port = int(os.getenv("QDRANT_PORT", 6333))
        self.collection_name = os.getenv(
            "QDRANT_COLLECTION",
            "kenya_law_reports"
        )

        self.client = QdrantClient(host=host, port=port)

    def write(self, batch: list[dict[str, Any]]):
        """
        Uploads points in batch.
        """
        points = []

        for row in batch:
            # Skip if embedding failed
            if "vector" not in row or not row["vector"]:
                continue

            # Construct Payload (Metadata)
            payload = {
                "text": row["text"],
                "filename": row["metadata"]["filename"],
                "page": row["metadata"].get("page_number", 0),
            }

            # Create Point
            points.append(
                models.PointStruct(
                    id=str(uuid.uuid4()),  # Generate unique ID for the vector
                    vector=row["vector"],
                    payload=payload,
                )
            )

        if points:
            # Upsert is atomic
            self.client.upsert(collection_name=self.collection_name, points=points)
