# pipelines/ingestion/indexing/qdrant.py
from qdrant_client import QdrantClient
from qdrant_client.http import models
import uuid

class QdrantIndexer:
    """Writes vectors to Qdrant using batch upserts."""
    def __init__(self, collection_name="rag_collection", vector_size=3):
        self.client = QdrantClient(host="192.168.214.21", port=6333)
        self.collection_name = collection_name
        self.vector_size = vector_size
        self._ensure_collection_exists()
    
    def _ensure_collection_exists(self):
        """Create collection if it doesn't exist."""
        try:
            # Check if collection exists
            self.client.get_collection(collection_name=self.collection_name)
            print(f"Collection '{self.collection_name}' already exists.")
        except Exception:
            # Collection doesn't exist, create it
            print(f"Creating collection '{self.collection_name}'...")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=models.VectorParams(
                    size=self.vector_size,
                    distance=models.Distance.COSINE
                )
            )
            print(f"Collection '{self.collection_name}' created successfully.")
    
    def write(self, batch):
        """Write a batch of vectors to Qdrant."""
        points = [
            models.PointStruct(
                id=str(uuid.uuid4()), 
                vector=row["vector"], 
                payload=row["metadata"]
            )
            for row in batch if "vector" in row
        ]
        
        if points:
            self.client.upsert(
                collection_name=self.collection_name, 
                points=points
            )
            print(f"Upserted {len(points)} points to '{self.collection_name}'")
        else:
            print("No valid vectors to upsert.")
        
        
if __name__ == "__main__":
    # Simple test
    indexer = QdrantIndexer(vector_size=3)  # Specify vector dimension
    test_batch = [
        {"vector": [0.1, 0.2, 0.3], "metadata": {"text": "Sample text 1"}},
        {"vector": [0.4, 0.5, 0.6], "metadata": {"text": "Sample text 2"}},
        {"vector": [0.45, 0.23, 0.67], "metadata": {"text": "Sample text 4"}},
    ]
    indexer.write(test_batch)