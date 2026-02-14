# pipelines/ingestion/main.py
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, List, Tuple

from minio import Minio

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
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def process_single_file(file_info: Tuple[str, bytes]) -> List[dict]:
    """
    Process a single file: parse PDF and chunk text.

    Args:
        file_info: (filename, file_bytes)

    Returns:
        List of chunks with metadata
    """
    filename, file_bytes = file_info

    try:
        logger.info(f"Processing: {filename}")

        # 1. Parse PDF
        text, metadata = parse_pdf_bytes(file_bytes, filename)
        logger.info(f"  Parsed {filename}: {len(text)} chars")

        # 2. Chunk text
        chunks = split_text(text, chunk_size=512, overlap=50)
        logger.info(f"  Chunked {filename}: {len(chunks)} chunks")

        # Add metadata to each chunk
        for chunk in chunks:
            chunk["metadata"].update(metadata)

        return chunks

    except Exception as e:
        logger.error(f"Failed to process {filename}: {e}")
        return []


def batch_embed(chunks: List[dict], batch_size: int = 50) -> List[dict]:
    """
    Generate embeddings for chunks in batches.

    Args:
        chunks: List of chunks with text and metadata
        batch_size: Number of chunks to embed at once

    Returns:
        List of chunks with embeddings added
    """
    embedder = BatchEmbedder()
    results = []
    total_batches = (len(chunks) - 1) // batch_size + 1

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        batch_num = i // batch_size + 1
        logger.info(f"Embedding batch {batch_num}/{total_batches} ({len(batch)} chunks)")

        try:
            batch_dict = {
                "text": [c["text"] for c in batch],
                "metadata": [c["metadata"] for c in batch]
            }

            result = embedder(batch_dict)

            # Add embeddings to chunks
            for j, chunk in enumerate(batch):
                chunk["vector"] = result["vector"][j]
                results.append(chunk)

        except Exception as e:
            logger.error(f"Failed to embed batch {batch_num}: {e}")
            continue

    return results


def batch_extract_graph(chunks: List[dict], batch_size: int = 1) -> List[dict]:
    """
    Extract graph data from chunks in batches.

    Args:
        chunks: List of chunks with text and metadata
        batch_size: Number of chunks to process at once

    Returns:
        List of chunks with graph data added
    """
    extractor = GraphExtractor()
    results = []
    total_batches = (len(chunks) - 1) // batch_size + 1

    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        batch_num = i // batch_size + 1
        logger.info(f"Extracting graph batch {batch_num}/{total_batches} ({len(batch)} chunks)")

        try:
            batch_dict = {
                "text": [c["text"] for c in batch],
                "metadata": [c["metadata"] for c in batch]
            }

            result = extractor(batch_dict)

            # Add graph data to chunks
            for j, chunk in enumerate(batch):
                chunk["graph_nodes"] = result["graph_nodes"][j]
                chunk["graph_edges"] = result["graph_edges"][j]
                results.append(chunk)

        except Exception as e:
            logger.error(f"Failed to extract graph for batch {batch_num}: {e}")
            continue

    return results


def main(bucket_name: str, prefix: str, max_workers: int = 4, enable_graph: bool = False):
    """
    Main ingestion workflow.

    Args:
        bucket_name: MinIO bucket name
        prefix: Prefix path for files to ingest
        max_workers: Number of parallel workers for file processing
        enable_graph: Whether to extract graph data (slow, optional)
    """
    logger.info(f"Starting ingestion: bucket={bucket_name}, prefix={prefix}, graph={enable_graph}")

    # 1. Connect to MinIO
    minio_endpoint = os.getenv("MINIO_ENDPOINT", "192.168.214.21:9000")
    minio_access_key = os.getenv("MINIO_ACCESS_KEY", "minioadmin")
    minio_secret_key = os.getenv("MINIO_SECRET_KEY", "minioadmin")

    client = Minio(
        minio_endpoint,
        access_key=minio_access_key,
        secret_key=minio_secret_key,
        secure=False
    )

    # 2. List and download files
    logger.info("Listing files from MinIO...")
    objects = list(client.list_objects(bucket_name, prefix=prefix, recursive=True))
    logger.info(f"Found {len(objects)} files")

    if not objects:
        logger.warning("No files found!")
        return

    logger.info("Downloading files...")
    files_to_process = []
    for obj in objects:
        try:
            response = client.get_object(bucket_name, obj.object_name)
            file_bytes = response.read()
            response.close()
            files_to_process.append((obj.object_name, file_bytes))
            logger.debug(f"Downloaded {obj.object_name}: {len(file_bytes)} bytes")
        except Exception as e:
            logger.error(f"Failed to download {obj.object_name}: {e}")

    logger.info(f"Downloaded {len(files_to_process)} files")

    # 3. Process files in parallel (parse + chunk)
    logger.info(f"Processing files with {max_workers} workers...")
    all_chunks = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(process_single_file, file_info)
                   for file_info in files_to_process]

        for future in as_completed(futures):
            try:
                chunks = future.result()
                all_chunks.extend(chunks)
            except Exception as e:
                logger.error(f"File processing failed: {e}")

    logger.info(f"Total chunks created: {len(all_chunks)}")

    if not all_chunks:
        logger.warning("No chunks to process!")
        return

    # 4. Generate embeddings (for vector search in Qdrant)
    logger.info("Generating embeddings...")
    chunks_with_vectors = batch_embed(all_chunks, batch_size=50)
    logger.info(f"Generated {len(chunks_with_vectors)} embeddings")

    # 5. Extract graph data (for Neo4j) - OPTIONAL
    chunks_with_graph = []
    if enable_graph:
        logger.info("Extracting graph data...")
        chunks_with_graph = batch_extract_graph(all_chunks, batch_size=10)
        logger.info(f"Extracted graph data for {len(chunks_with_graph)} chunks")
    else:
        logger.info("Skipping graph extraction (disabled)")

    # 6. Write vectors to Qdrant
    logger.info("Writing vectors to Qdrant...")
    qdrant_indexer = QdrantIndexer()
    vector_count = 0

    for i in range(0, len(chunks_with_vectors), 100):
        batch = chunks_with_vectors[i:i + 100]

        try:
            qdrant_indexer.write(batch)  # Pass list directly, not dict
            vector_count += len(batch)
            logger.info(f"Indexed {vector_count}/{len(chunks_with_vectors)} vectors to Qdrant")
        except Exception as e:
            logger.error(f"Failed to write batch to Qdrant: {e}")
            import traceback
            logger.error(traceback.format_exc())

    # 7. Write graph to Neo4j (if enabled)
    graph_count = 0
    if enable_graph and chunks_with_graph:
        logger.info("Writing graph to Neo4j...")
        neo4j_indexer = Neo4jIndexer()

        for i in range(0, len(chunks_with_graph), 100):
            batch = chunks_with_graph[i:i + 100]

            try:
                neo4j_indexer.write(batch)  # Pass list directly, not dict
                graph_count += len(batch)
                logger.info(f"Indexed {graph_count}/{len(chunks_with_graph)} graph entries to Neo4j")
            except Exception as e:
                logger.error(f"Failed to write batch to Neo4j: {e}")
                import traceback
                logger.error(traceback.format_exc())
    else:
        logger.info("Skipping Neo4j indexing (graph extraction disabled)")

    # 8. Summary
    print(f"\n{'='*60}")
    print(f"✓ Ingestion Completed Successfully!")
    print(f"{'='*60}")
    print(f"  Files processed:  {len(files_to_process)}")
    print(f"  Total chunks:     {len(all_chunks)}")
    print(f"  Vectors indexed:  {vector_count}")
    print(f"  Graph entries:    {graph_count}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python main.py <bucket_name> <prefix> [max_workers] [--enable-graph]")
        print("Example: python main.py srtmanager kenya_law_data/case 4")
        print("Example with graph: python main.py srtmanager kenya_law_data/case 4 --enable-graph")
        sys.exit(1)

    bucket = sys.argv[1]
    prefix = sys.argv[2]

    # Parse optional arguments
    workers = int(os.getenv("MAX_WORKERS", "4"))
    enable_graph = os.getenv("ENABLE_GRAPH", "false").lower() == "true"

    for i in range(3, len(sys.argv)):
        arg = sys.argv[i]
        if arg == "--enable-graph":
            enable_graph = True
        elif arg.isdigit():
            workers = int(arg)

    main(bucket, prefix, max_workers=workers, enable_graph=enable_graph)
