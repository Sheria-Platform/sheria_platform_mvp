# pipelines/ingestion/embedding/compute.py
import httpx

class BatchEmbedder:
    """Ray Actor that batches text chunks and calls the Embedding Service."""
    def __init__(self):
        # We point to the internal K8s service DNS
        self.endpoint = "http://ray-serve-embed:8000/embed"
        self.client = httpx.Client(timeout=30.0)
    def __call__(self, batch):
        """Sends a batch of text to the GPU service."""
        response = self.client.post(
            self.endpoint, 
            json={"text": batch["text"], "task_type": "document"}
        )
        batch["vector"] = response.json()["embeddings"]
        return batch