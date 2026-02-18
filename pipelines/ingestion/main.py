# pipelines/ingestion/main.py
"""
Sheria Platform Ingestion Pipeline

This module orchestrates the end-to-end ingestion of legal documents into the
Sheria Platform. It handles document loading from MinIO, parsing (PDF/DOCX/HTML),
text chunking, embedding generation, graph extraction, and indexing to Qdrant
and Neo4j databases.

Architecture:
    1. Load documents from MinIO bucket
    2. Parse and chunk documents in parallel
    3. Fork A: Generate embeddings (Ollama) -> Index to Qdrant
    4. Fork B: Extract graph data (Ollama LLM) -> Index to Neo4j

Usage:
    python main.py <bucket_name> <prefix> [max_workers] [--enable-graph]

Example:
    python main.py srtmanager kenya_law_data/case 4
    python main.py srtmanager kenya_law_data/case 4 --enable-graph

Environment Variables:
    See .env.example for required configuration
"""
import logging
import os
import signal
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional, Tuple

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
    level=os.getenv("LOG_LEVEL", "INFO"),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(os.path.dirname(__file__), "logs", "ingestion.log"))
    ] if os.path.exists(os.path.join(os.path.dirname(__file__), "logs")) else [logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Graceful shutdown flag
_shutdown_requested = False


def signal_handler(signum: int, frame: Any) -> None:
    """
    Handle shutdown signals gracefully.

    Args:
        signum: Signal number
        frame: Current stack frame
    """
    global _shutdown_requested
    logger.warning(f"Received shutdown signal {signum}. Finishing current batch and shutting down...")
    _shutdown_requested = True


def validate_config() -> Dict[str, Any]:
    """
    Validate and load configuration from environment variables.

    Returns:
        Dictionary containing validated configuration

    Raises:
        ValueError: If required configuration is missing or invalid
    """
    config = {
        "minio_endpoint": os.getenv("MINIO_ENDPOINT", "192.168.214.21:9000"),
        "minio_access_key": os.getenv("MINIO_ACCESS_KEY", "minioadmin"),
        "minio_secret_key": os.getenv("MINIO_SECRET_KEY", "minioadmin"),
        "minio_secure": os.getenv("MINIO_SECURE", "false").lower() == "true",
        "chunk_size": int(os.getenv("CHUNK_SIZE", "512")),
        "chunk_overlap": int(os.getenv("CHUNK_OVERLAP", "50")),
        "max_workers": int(os.getenv("MAX_WORKERS", "4")),
        "enable_graph": os.getenv("ENABLE_GRAPH", "false").lower() == "true",
        "embedding_batch_size": int(os.getenv("EMBEDDING_BATCH_SIZE", "50")),
        "graph_batch_size": int(os.getenv("GRAPH_BATCH_SIZE", "10")),
        "max_file_size_mb": int(os.getenv("MAX_FILE_SIZE_MB", "100")),
    }

    # Validate ranges
    if config["chunk_size"] < 50 or config["chunk_size"] > 8192:
        raise ValueError(f"chunk_size must be between 50 and 8192, got {config['chunk_size']}")
    if config["chunk_overlap"] < 0 or config["chunk_overlap"] >= config["chunk_size"]:
        raise ValueError(f"chunk_overlap must be between 0 and chunk_size, got {config['chunk_overlap']}")
    if config["max_workers"] < 1 or config["max_workers"] > 32:
        raise ValueError(f"max_workers must be between 1 and 32, got {config['max_workers']}")

    logger.info("Configuration validated successfully")
    logger.debug(f"Config: {config}")

    return config


def process_single_file(file_info: Tuple[str, bytes], config: Dict[str, Any]) -> Tuple[List[dict], Optional[str]]:
    """
    Process a single file: parse PDF and chunk text.

    Args:
        file_info: Tuple of (filename, file_bytes)
        config: Configuration dictionary with chunk_size, chunk_overlap, max_file_size_mb

    Returns:
        Tuple of (list of chunks with metadata, error_message if failed)

    Note:
        Returns empty list with error message on failure instead of raising
        to allow pipeline to continue processing other files.
    """
    filename, file_bytes = file_info

    try:
        # Validate file size
        file_size_mb = len(file_bytes) / (1024 * 1024)
        if file_size_mb > config["max_file_size_mb"]:
            error = f"File too large: {file_size_mb:.2f} MB (max: {config['max_file_size_mb']} MB)"
            logger.warning(f"{filename}: {error}")
            return [], error

        logger.info(f"Processing: {filename} ({file_size_mb:.2f} MB)")

        # 1. Parse PDF
        text, metadata = parse_pdf_bytes(file_bytes, filename)
        logger.info(f"  Parsed {filename}: {len(text)} chars")

        # Validate extracted text
        if not text or len(text.strip()) == 0:
            error = "No text content extracted from file"
            logger.warning(f"{filename}: {error}")
            return [], error

        # 2. Chunk text
        chunks = split_text(
            text,
            chunk_size=config["chunk_size"],
            overlap=config["chunk_overlap"]
        )
        logger.info(f"  Chunked {filename}: {len(chunks)} chunks")

        # Add metadata to each chunk
        for chunk in chunks:
            chunk["metadata"].update(metadata)
            chunk["metadata"]["source_file"] = filename

        return chunks, None

    except Exception as e:
        error = f"Failed to process: {str(e)}"
        logger.error(f"{filename}: {error}", exc_info=True)
        return [], error


def batch_embed(chunks: List[dict], batch_size: int, max_retries: int = 3) -> Tuple[List[dict], int]:
    """
    Generate embeddings for chunks in batches with retry logic.

    Args:
        chunks: List of chunks with text and metadata
        batch_size: Number of chunks to embed at once
        max_retries: Maximum number of retries for failed batches

    Returns:
        Tuple of (list of chunks with embeddings added, number of failed chunks)

    Note:
        Failed batches are logged but pipeline continues. Chunks without
        embeddings are excluded from results.
    """
    if not chunks:
        logger.warning("No chunks provided for embedding")
        return [], 0

    embedder = BatchEmbedder()
    results = []
    failed_count = 0
    total_batches = (len(chunks) - 1) // batch_size + 1

    for i in range(0, len(chunks), batch_size):
        if _shutdown_requested:
            logger.warning("Shutdown requested, stopping embedding generation")
            break

        batch = chunks[i:i + batch_size]
        batch_num = i // batch_size + 1
        logger.info(f"Embedding batch {batch_num}/{total_batches} ({len(batch)} chunks)")

        success = False
        for attempt in range(max_retries):
            try:
                batch_dict = {
                    "text": [c["text"] for c in batch],
                    "metadata": [c["metadata"] for c in batch]
                }

                result = embedder(batch_dict)

                # Validate result structure
                if "vector" not in result or len(result["vector"]) != len(batch):
                    raise ValueError(f"Invalid embedding response: expected {len(batch)} vectors")

                # Add embeddings to chunks
                for j, chunk in enumerate(batch):
                    chunk["vector"] = result["vector"][j]
                    results.append(chunk)

                success = True
                break

            except Exception as e:
                logger.warning(f"Embedding batch {batch_num} failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    logger.error(f"Failed to embed batch {batch_num} after {max_retries} attempts")
                    failed_count += len(batch)

        if not success:
            logger.error(f"Skipping batch {batch_num} ({len(batch)} chunks)")

    embedder.close()  # Cleanup resources
    logger.info(f"Embedding complete: {len(results)} successful, {failed_count} failed")
    return results, failed_count


def batch_extract_graph(chunks: List[dict], batch_size: int, max_retries: int = 3) -> Tuple[List[dict], int]:
    """
    Extract graph data from chunks in batches with retry logic.

    Args:
        chunks: List of chunks with text and metadata
        batch_size: Number of chunks to process at once
        max_retries: Maximum number of retries for failed batches

    Returns:
        Tuple of (list of chunks with graph data added, number of failed chunks)

    Note:
        Failed batches are logged but pipeline continues. Chunks with empty
        graph data are still included in results.
    """
    if not chunks:
        logger.warning("No chunks provided for graph extraction")
        return [], 0

    extractor = GraphExtractor()
    results = []
    failed_count = 0
    total_batches = (len(chunks) - 1) // batch_size + 1

    for i in range(0, len(chunks), batch_size):
        if _shutdown_requested:
            logger.warning("Shutdown requested, stopping graph extraction")
            break

        batch = chunks[i:i + batch_size]
        batch_num = i // batch_size + 1
        logger.info(f"Extracting graph batch {batch_num}/{total_batches} ({len(batch)} chunks)")

        success = False
        for attempt in range(max_retries):
            try:
                batch_dict = {
                    "text": [c["text"] for c in batch],
                    "metadata": [c["metadata"] for c in batch]
                }

                result = extractor(batch_dict)

                # Validate result structure
                if "graph_nodes" not in result or "graph_edges" not in result:
                    raise ValueError("Invalid graph extraction response structure")
                if len(result["graph_nodes"]) != len(batch) or len(result["graph_edges"]) != len(batch):
                    raise ValueError(f"Graph response length mismatch: expected {len(batch)}")

                # Add graph data to chunks
                for j, chunk in enumerate(batch):
                    chunk["graph_nodes"] = result["graph_nodes"][j]
                    chunk["graph_edges"] = result["graph_edges"][j]
                    results.append(chunk)

                success = True
                break

            except Exception as e:
                logger.warning(f"Graph extraction batch {batch_num} failed (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt == max_retries - 1:
                    logger.error(f"Failed to extract graph for batch {batch_num} after {max_retries} attempts")
                    failed_count += len(batch)

        if not success:
            # Add chunks with empty graph data to maintain consistency
            for chunk in batch:
                chunk["graph_nodes"] = []
                chunk["graph_edges"] = []
                results.append(chunk)
            logger.error(f"Added batch {batch_num} with empty graph data")

    extractor.close()  # Cleanup resources
    logger.info(f"Graph extraction complete: {len(results) - failed_count} successful, {failed_count} with empty data")
    return results, failed_count


def main(bucket_name: str, prefix: str, max_workers: Optional[int] = None, enable_graph: Optional[bool] = None) -> int:
    """
    Main ingestion workflow with production-grade error handling.

    This function orchestrates the complete document ingestion pipeline:
    1. Validates configuration and inputs
    2. Loads documents from MinIO
    3. Parses and chunks documents in parallel
    4. Generates embeddings and indexes to Qdrant
    5. (Optional) Extracts graph data and indexes to Neo4j

    Args:
        bucket_name: MinIO bucket name (required, non-empty string)
        prefix: Prefix path for files to ingest (required, non-empty string)
        max_workers: Number of parallel workers for file processing (1-32, default from config)
        enable_graph: Whether to extract graph data (slow, optional, default from config)

    Returns:
        Exit code: 0 for success, 1 for failure

    Raises:
        ValueError: If required parameters are invalid
        Exception: For critical failures that prevent pipeline execution

    Example:
        >>> main("srtmanager", "kenya_law_data/case", max_workers=4, enable_graph=False)
        0
    """
    # Install signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Validate inputs
    if not bucket_name or not isinstance(bucket_name, str):
        raise ValueError(f"bucket_name must be a non-empty string, got: {bucket_name}")
    if not prefix or not isinstance(prefix, str):
        raise ValueError(f"prefix must be a non-empty string, got: {prefix}")

    # Load and validate configuration
    try:
        config = validate_config()
    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        return 1

    # Override config with provided arguments
    if max_workers is not None:
        if max_workers < 1 or max_workers > 32:
            raise ValueError(f"max_workers must be between 1 and 32, got {max_workers}")
        config["max_workers"] = max_workers

    if enable_graph is not None:
        config["enable_graph"] = enable_graph

    logger.info(f"Starting ingestion: bucket={bucket_name}, prefix={prefix}")
    logger.info(f"Configuration: workers={config['max_workers']}, graph={config['enable_graph']}, "
                f"chunk_size={config['chunk_size']}, overlap={config['chunk_overlap']}")

    # Statistics tracking
    stats = {
        "files_found": 0,
        "files_downloaded": 0,
        "files_processed": 0,
        "files_failed": 0,
        "chunks_created": 0,
        "vectors_indexed": 0,
        "vectors_failed": 0,
        "graph_indexed": 0,
        "graph_failed": 0,
    }

    try:
        # 1. Connect to MinIO
        logger.info("Connecting to MinIO...")
        client = Minio(
            config["minio_endpoint"],
            access_key=config["minio_access_key"],
            secret_key=config["minio_secret_key"],
            secure=config["minio_secure"]
        )

        # Test connection
        if not client.bucket_exists(bucket_name):
            raise ValueError(f"Bucket '{bucket_name}' does not exist")
        logger.info(f"Connected to MinIO bucket: {bucket_name}")

        # 2. List and download files
        logger.info("Listing files from MinIO...")
        try:
            objects = list(client.list_objects(bucket_name, prefix=prefix, recursive=True))
        except Exception as e:
            logger.error(f"Failed to list objects: {e}")
            return 1

        stats["files_found"] = len(objects)
        logger.info(f"Found {stats['files_found']} files")

        if not objects:
            logger.warning("No files found!")
            return 0  # Not an error, just nothing to process

        logger.info("Downloading files...")
        files_to_process = []
        for obj in objects:
            if _shutdown_requested:
                logger.warning("Shutdown requested, stopping file download")
                break

            try:
                response = client.get_object(bucket_name, obj.object_name)
                file_bytes = response.read()
                response.close()
                files_to_process.append((obj.object_name, file_bytes))
                stats["files_downloaded"] += 1
                logger.debug(f"Downloaded {obj.object_name}: {len(file_bytes)} bytes")
            except Exception as e:
                logger.error(f"Failed to download {obj.object_name}: {e}")
                stats["files_failed"] += 1

        logger.info(f"Downloaded {stats['files_downloaded']}/{stats['files_found']} files successfully")

        # 3. Process files in parallel (parse + chunk)
        logger.info(f"Processing files with {config['max_workers']} workers...")
        all_chunks = []
        processing_errors = []

        with ThreadPoolExecutor(max_workers=config['max_workers']) as executor:
            futures = [executor.submit(process_single_file, file_info, config)
                       for file_info in files_to_process]

            for future in as_completed(futures):
                if _shutdown_requested:
                    logger.warning("Shutdown requested, cancelling remaining file processing")
                    for f in futures:
                        f.cancel()
                    break

                try:
                    chunks, error = future.result()
                    if chunks:
                        all_chunks.extend(chunks)
                        stats["files_processed"] += 1
                    if error:
                        processing_errors.append(error)
                        stats["files_failed"] += 1
                except Exception as e:
                    logger.error(f"File processing future failed: {e}", exc_info=True)
                    stats["files_failed"] += 1

        stats["chunks_created"] = len(all_chunks)
        logger.info(f"File processing complete: {stats['files_processed']} successful, {stats['files_failed']} failed")
        logger.info(f"Total chunks created: {stats['chunks_created']}")

        if processing_errors:
            logger.warning(f"Processing errors encountered: {len(processing_errors)}")
            for error in processing_errors[:10]:  # Log first 10 errors
                logger.debug(f"  - {error}")

        if not all_chunks:
            logger.warning("No chunks to process!")
            return 0 if _shutdown_requested else 1

        # 4. Generate embeddings (for vector search in Qdrant)
        if _shutdown_requested:
            logger.warning("Shutdown requested, skipping embedding generation")
            return 1

        logger.info("Generating embeddings...")
        chunks_with_vectors, embedding_failures = batch_embed(
            all_chunks,
            batch_size=config["embedding_batch_size"],
            max_retries=3
        )
        stats["vectors_failed"] = embedding_failures
        logger.info(f"Generated {len(chunks_with_vectors)} embeddings ({embedding_failures} failed)")

        # 5. Extract graph data (for Neo4j) - OPTIONAL
        chunks_with_graph = []
        if config["enable_graph"]:
            if _shutdown_requested:
                logger.warning("Shutdown requested, skipping graph extraction")
                return 1

            logger.info("Extracting graph data...")
            chunks_with_graph, graph_failures = batch_extract_graph(
                all_chunks,
                batch_size=config["graph_batch_size"],
                max_retries=3
            )
            stats["graph_failed"] = graph_failures
            logger.info(f"Extracted graph data for {len(chunks_with_graph)} chunks ({graph_failures} with empty data)")
        else:
            logger.info("Skipping graph extraction (disabled)")

        # 6. Write vectors to Qdrant
        if chunks_with_vectors:
            if _shutdown_requested:
                logger.warning("Shutdown requested, skipping Qdrant indexing")
                return 1

            logger.info("Writing vectors to Qdrant...")
            qdrant_indexer = QdrantIndexer()
            qdrant_batch_size = 100

            for i in range(0, len(chunks_with_vectors), qdrant_batch_size):
                if _shutdown_requested:
                    logger.warning("Shutdown requested, stopping Qdrant indexing")
                    break

                batch = chunks_with_vectors[i:i + qdrant_batch_size]

                for attempt in range(3):  # Retry logic
                    try:
                        qdrant_indexer.write(batch)
                        stats["vectors_indexed"] += len(batch)
                        logger.info(f"Indexed {stats['vectors_indexed']}/{len(chunks_with_vectors)} vectors to Qdrant")
                        break
                    except Exception as e:
                        logger.warning(f"Failed to write batch to Qdrant (attempt {attempt + 1}/3): {e}")
                        if attempt == 2:
                            logger.error(f"Failed to index batch after 3 attempts", exc_info=True)

            qdrant_indexer.close()  # Cleanup
        else:
            logger.warning("No vectors to index to Qdrant")

        # 7. Write graph to Neo4j (if enabled)
        if config["enable_graph"] and chunks_with_graph:
            if _shutdown_requested:
                logger.warning("Shutdown requested, skipping Neo4j indexing")
                return 1

            logger.info("Writing graph to Neo4j...")
            neo4j_indexer = Neo4jIndexer()
            neo4j_batch_size = 100

            for i in range(0, len(chunks_with_graph), neo4j_batch_size):
                if _shutdown_requested:
                    logger.warning("Shutdown requested, stopping Neo4j indexing")
                    break

                batch = chunks_with_graph[i:i + neo4j_batch_size]

                for attempt in range(3):  # Retry logic
                    try:
                        neo4j_indexer.write(batch)
                        stats["graph_indexed"] += len(batch)
                        logger.info(f"Indexed {stats['graph_indexed']}/{len(chunks_with_graph)} graph entries to Neo4j")
                        break
                    except Exception as e:
                        logger.warning(f"Failed to write batch to Neo4j (attempt {attempt + 1}/3): {e}")
                        if attempt == 2:
                            logger.error(f"Failed to index graph batch after 3 attempts", exc_info=True)

            neo4j_indexer.close()  # Cleanup
        else:
            logger.info("Skipping Neo4j indexing (graph extraction disabled or no data)")

        # 8. Summary
        print(f"\n{'='*60}")
        status = "✓ Ingestion Completed" if not _shutdown_requested else "⚠ Ingestion Interrupted"
        print(f"{status}")
        print(f"{'='*60}")
        print(f"  Files found:      {stats['files_found']}")
        print(f"  Files downloaded: {stats['files_downloaded']}")
        print(f"  Files processed:  {stats['files_processed']}")
        print(f"  Files failed:     {stats['files_failed']}")
        print(f"  Total chunks:     {stats['chunks_created']}")
        print(f"  Vectors indexed:  {stats['vectors_indexed']}")
        print(f"  Vectors failed:   {stats['vectors_failed']}")
        if config["enable_graph"]:
            print(f"  Graph indexed:    {stats['graph_indexed']}")
            print(f"  Graph empty:      {stats['graph_failed']}")
        print(f"{'='*60}\n")

        return 0 if stats['files_processed'] > 0 else 1

    except KeyboardInterrupt:
        logger.warning("Received keyboard interrupt, shutting down...")
        return 130  # Standard exit code for SIGINT
    except Exception as e:
        logger.error(f"Fatal error in ingestion pipeline: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    """
    CLI entry point for the ingestion pipeline.

    Parses command-line arguments and invokes the main ingestion workflow.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="Sheria Platform Ingestion Pipeline - Process legal documents for RAG",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic ingestion (embeddings only, fast)
  python main.py srtmanager kenya_law_data/case

  # With custom worker count
  python main.py srtmanager kenya_law_data/case --max-workers 8

  # With graph extraction (slow)
  python main.py srtmanager kenya_law_data/case --enable-graph

  # Full configuration
  python main.py srtmanager kenya_law_data/case --max-workers 8 --enable-graph

Environment Variables:
  See .env.example for all available configuration options.
  CLI arguments override environment variables.
        """
    )

    parser.add_argument(
        "bucket_name",
        type=str,
        help="MinIO bucket name containing documents to ingest"
    )

    parser.add_argument(
        "prefix",
        type=str,
        help="Prefix path for files to ingest (e.g., 'kenya_law_data/case')"
    )

    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="Number of parallel workers for file processing (1-32, default: from config)"
    )

    parser.add_argument(
        "--enable-graph",
        action="store_true",
        default=None,
        help="Enable graph extraction (slow, default: from config)"
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=os.getenv("LOG_LEVEL", "INFO"),
        help="Logging level (default: INFO)"
    )

    args = parser.parse_args()

    # Set log level
    logging.getLogger().setLevel(args.log_level)

    # Run pipeline
    try:
        exit_code = main(
            bucket_name=args.bucket_name,
            prefix=args.prefix,
            max_workers=args.max_workers,
            enable_graph=args.enable_graph
        )
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)
    