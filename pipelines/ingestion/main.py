# pipelines/ingestion/main.py
import logging
import os
from typing import Any

import ray

from pipelines.ingestion.chunking.splitter_chunking import split_text
from pipelines.ingestion.embedding.embedding_compute import BatchEmbedder
from pipelines.ingestion.graph.extractor_graph import GraphExtractor
from pipelines.ingestion.indexing.neo4j_indexing import Neo4jIndexer
from pipelines.ingestion.indexing.qdrant_indexing import QdrantIndexer
from pipelines.ingestion.loaders.pdf_loader import parse_pdf_bytes

# Load environment variables from .env file if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Initialize Ray
ray_address = os.getenv("RAY_ADDRESS", "auto")
if not ray.is_initialized():
    ray.init(address=ray_address)

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def process_batch(batch: dict[str, Any]) -> dict[str, Any]:
    """
    Ray Data transformation function.
    Receives a batch of file contents (S3 bytes).
    """
    results = []

    for i, content in enumerate(batch["bytes"]):
        filename = batch["filename"][i]

        # 1. Parsing (CPU Intensive)
        # We use a helper function to handle PDF/DOCX/HTML logic
        raw_text, metadata = parse_pdf_bytes(content, filename)

        # 2. Chunking (CPU)
        chunks = split_text(raw_text, chunk_size=512, overlap=50)

        # Add metadata to each chunk
        for chunk in chunks:
            chunk["metadata"].update(metadata)
            results.append(chunk)

    return {
        "text": [r["text"] for r in results],
        "metadata": [r["metadata"] for r in results],
    }


def main(bucket_name: str, prefix: str):
    """
    Main Orchestration Flow.
    """
    # 1. Read from S3 using Ray Data (Lazy Loading)
    # This automatically distributes reading across workers
    ds = ray.data.read_binary_files(
        paths=f"s3://{bucket_name}/{prefix}", include_paths=True
    )

    # 2. Parse & Chunk (Map Phase)
    # num_cpus=1 tells Ray to reserve 1 CPU core per parsing task
    chunked_ds = ds.map_batches(
        process_batch,
        batch_size=10,  # Process 10 files at a time per worker
        num_cpus=1,
    )

    # 3. FORK: Branch A - Vector Embeddings (GPU Intensive)
    # We use a Class Actor (BatchEmbedder) to maintain connection to Ray Serve
    vector_ds = chunked_ds.map_batches(
        BatchEmbedder,
        concurrency=5,  # Run 5 concurrent embedders
        num_gpus=0.2,  # Each embedder needs minimal GPU access (Ray Serve handles heavy lift)
        batch_size=100,  # Batch 100 chunks for vectorization
    )

    # 4. FORK: Branch B - Graph Extraction (LLM Intensive)
    # This is slower, so we might set higher concurrency or dedicate nodes
    graph_ds = chunked_ds.map_batches(
        GraphExtractor,
        concurrency=10,
        num_gpus=0.5,  # Needs significant LLM inference power
        batch_size=5,
    )

    # 5. Indexing (Write to DBs)
    # Trigger execution
    vector_ds.write_datasource(QdrantIndexer())
    graph_ds.write_datasource(Neo4jIndexer())

    print("Ingestion Job Completed Successfully.")


if __name__ == "__main__":
    # In a real run, these args come from the job submission
    import sys

    main(sys.argv[1], sys.argv[2])
