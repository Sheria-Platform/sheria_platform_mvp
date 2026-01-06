# pipelines/ingestion/indexing/qdrant.py
from qdrant_client import QdrantClient
from qdrant_client.http import models
import uuid

class QdrantIndexer:
    """Writes vectors to Qdrant using batch upserts."""
    def __init__(self):
        self.client = QdrantClient(host="qdrant-service", port=6333)
    def write(self, batch):
        points = [
            models.PointStruct(id=str(uuid.uuid4()), vector=row["vector"], payload=row["metadata"])
            for row in batch if "vector" in row
        ]
        self.client.upsert(collection_name="rag_collection", points=points)