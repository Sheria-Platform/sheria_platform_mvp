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

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Ray
ray_address = os.getenv("RAY_ADDRESS", "local")
if not ray.is_initialized():
    try:
        # Try to connect to existing cluster if address is specified
        if ray_address != "local":
            ray.init(address=ray_address)
        else:
            # Start local Ray instance for testing with more CPUs
            ray.init(num_cpus=8, ignore_reinit_error=True)
            logger.info("Started local Ray instance with 8 CPUs")
    except ConnectionError:
        # Fallback to local if cluster connection fails
        ray.init(num_cpus=8, ignore_reinit_error=True)
        logger.info("Could not connect to Ray cluster, started local instance with 8 CPUs")


def process_batch(batch: dict[str, Any]) -> dict[str, Any]:
    """
    Ray Data transformation function.
    Receives a batch of file contents (S3 bytes).
    """
    results = []

    # Ray's read_binary_files returns "bytes" and "path" keys
    for i, content in enumerate(batch["bytes"]):
        filepath = batch["path"][i] if "path" in batch else f"file_{i}"

        # 1. Parsing (CPU Intensive)
        # We use a helper function to handle PDF/DOCX/HTML logic
        raw_text, metadata = parse_pdf_bytes(content, filepath)

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
    # Configure MinIO/S3 connection
    import pyarrow.fs as fs

    minio_endpoint = os.getenv("MINIO_ENDPOINT", "192.168.214.21:9000")
    minio_access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")
    minio_secure = os.getenv("MINIO_SECURE", "false").lower() == "true"

    # Create S3 filesystem for MinIO
    s3_fs = fs.S3FileSystem(
        endpoint_override=minio_endpoint,
        access_key=minio_access_key,
        secret_key=minio_secret_key,
        scheme="http" if not minio_secure else "https"
    )

    # 1. Read from MinIO using Ray Data (Lazy Loading)
    # This automatically distributes reading across workers
    ds = ray.data.read_binary_files(
        paths=f"s3://{bucket_name}/{prefix}",
        filesystem=s3_fs,
        include_paths=True
    )

    # 2. Parse & Chunk (Map Phase)
    # num_cpus=1 tells Ray to reserve 1 CPU core per parsing task
    chunked_ds = ds.map_batches(
        process_batch,
        batch_size=10,  # Process 10 files at a time per worker
        num_cpus=1,
    )

    # 3. FORK: Branch A - Vector Embeddings (via remote Ollama)
    # We use a Class Actor (BatchEmbedder) to call remote Ollama
    # Set runtime environment for Ray actors to ensure they have access to env vars
    vector_ds = chunked_ds.map_batches(
        BatchEmbedder,
        concurrency=3,  # Run 3 concurrent embedders
        batch_size=100,  # Batch 100 chunks for vectorization
        fn_constructor_kwargs={},  # Ensure class is instantiated with current env
    )

    # 4. FORK: Branch B - Graph Extraction (via remote Ollama)
    # This is slower, so we might set higher concurrency
    graph_ds = chunked_ds.map_batches(
        GraphExtractor,
        concurrency=3,  # Reduced concurrency for LLM calls
        batch_size=5,
    )

    # 5. Indexing (Write to DBs)
    # Trigger execution - consume the datasets and write to databases
    qdrant_indexer = QdrantIndexer()
    neo4j_indexer = Neo4jIndexer()

    # Write vectors to Qdrant
    logger.info("Writing vectors to Qdrant...")
    vector_count = 0
    for batch in vector_ds.iter_batches(batch_size=100):
        qdrant_indexer.write(batch)
        vector_count += len(batch)
        logger.info(f"Indexed {vector_count} vectors to Qdrant")

    # Write graph to Neo4j
    logger.info("Writing graph to Neo4j...")
    graph_count = 0
    for batch in graph_ds.iter_batches(batch_size=100):
        neo4j_indexer.write(batch)
        graph_count += len(batch)
        logger.info(f"Indexed {graph_count} graph entries to Neo4j")

    print(f"\n✓ Ingestion Job Completed Successfully!")
    print(f"  - Vectors indexed: {vector_count}")
    print(f"  - Graph entries indexed: {graph_count}")


if __name__ == "__main__":
    # In a real run, these args come from the job submission
    import sys

    main(sys.argv[1], sys.argv[2])
