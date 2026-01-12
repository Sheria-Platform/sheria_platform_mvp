# pipelines/ingestion/embedding/compute.py
import httpx

class BatchEmbedder:
    """Ray Actor that batches text chunks and calls the Embedding Service."""
    def __init__(self):
        # We point to the internal K8s service DNS
        self.endpoint = "http://192.168.214.21:11434/api/embeddings"
        self.client = httpx.Client(timeout=30.0)
    def __call__(self, batch):
        """Sends a batch of text to the GPU service."""
        response = self.client.post(
            self.endpoint, 
            json={"prompt": batch["text"], "task_type": "document", "model": "nomic-embed-text"}
        )
        print(response.json())
        batch["vector"] = response.json()["embedding"]
        return batch
    
if __name__ == "__main__":
    # Example usage
    embedder = BatchEmbedder()
    sample_batch = {"text": "Hello world Ray is great for scaling"}
    result = embedder(sample_batch)
    print(result)
    