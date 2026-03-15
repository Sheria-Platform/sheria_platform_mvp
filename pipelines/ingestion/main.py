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
    python main.py legal-documents legal/kenya_law/ 4
    python main.py legal-documents legal/kenya_law/ 4 --enable-graph

Environment Variables:
    See .env.example for required configuration
"""

import logging
import os
import signal
import sys
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional

from minio import Minio

from pipelines.ingestion.chunking.metadata_chunking import enrich_metadata
from pipelines.ingestion.chunking.splitter_chunking import split_text
from pipelines.ingestion.embedding.embedding_compute import BatchEmbedder
from pipelines.ingestion.graph.extractor_graph import GraphExtractor
from pipelines.ingestion.indexing.neo4j_indexing import Neo4jIndexer
from pipelines.ingestion.indexing.qdrant_indexing import QdrantIndexer
from pipelines.ingestion.loaders.dispatcher import SUPPORTED_EXTENSIONS, get_loader

# Load environment variables from .env file if present
try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

# Setup logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(
            os.path.join(os.path.dirname(__file__), "logs", "ingestion.log")
        ),
    ]
    if os.path.exists(os.path.join(os.path.dirname(__file__), "logs"))
    else [logging.StreamHandler()],
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
    logger.warning(
        f"Received shutdown signal {signum}. Finishing current batch and shutting down..."
    )
    _shutdown_requested = True


def validate_config() -> dict[str, Any]:
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
        "file_batch_size": int(os.getenv("FILE_BATCH_SIZE", "20")),
    }

    # Validate ranges
    if config["chunk_size"] < 50 or config["chunk_size"] > 8192:
        raise ValueError(
            f"chunk_size must be between 50 and 8192, got {config['chunk_size']}"
        )
    if config["chunk_overlap"] < 0 or config["chunk_overlap"] >= config["chunk_size"]:
        raise ValueError(
            f"chunk_overlap must be between 0 and chunk_size, got {config['chunk_overlap']}"
        )
    if config["max_workers"] < 1 or config["max_workers"] > 32:
        raise ValueError(
            f"max_workers must be between 1 and 32, got {config['max_workers']}"
        )
    if config["file_batch_size"] < 1 or config["file_batch_size"] > 500:
        raise ValueError(
            f"file_batch_size must be between 1 and 500, got {config['file_batch_size']}"
        )

    logger.info("Configuration validated successfully")
    logger.debug(f"Config: {config}")

    return config


COURT_NAMES = {
    "kehc": "High Court",
    "keelc": "Environment and Land Court",
    "keic": "Industrial Court",
    "keca": "Court of Appeal",
    "kesc": "Supreme Court",
    "kehcc": "Constitutional and Human Rights Division",
}


def extract_path_metadata(object_path: str) -> dict:
    """
    Parse MinIO object path into legal document metadata.

    Expected: legal/kenya_law/{year}/{case_slug}/{citation_code}.pdf
    Returns:  source, year, case_slug, citation_code, court_code, court_name, case_number
    """
    metadata = {}
    parts = object_path.replace("\\", "/").split("/")
    try:
        if len(parts) >= 5 and parts[0] == "legal" and parts[1] == "kenya_law":
            metadata["source"] = "kenya_law"
            metadata["year"] = parts[2]
            metadata["case_slug"] = parts[3]
            citation_code = parts[4].rsplit(".", 1)[0]  # strip .pdf
            metadata["citation_code"] = citation_code
            # citation format: {court_code}_{year}_{number}
            cp = citation_code.rsplit("_", 2)
            if len(cp) == 3:
                metadata["court_code"] = cp[0]
                metadata["case_number"] = cp[2]
                metadata["court_name"] = COURT_NAMES.get(cp[0], cp[0].upper())
    except Exception:
        pass  # non-standard paths — degrade gracefully
    return metadata


def process_single_file(
    file_info: tuple[str, bytes], config: dict[str, Any]
) -> tuple[list[dict], str | None]:
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

        # 1. Dispatch to the correct loader by file extension
        loader = get_loader(filename)
        text, metadata = loader(file_bytes, filename)
        logger.info(f"  Parsed {filename}: {len(text)} chars")

        # Validate extracted text
        if not text or len(text.strip()) == 0:
            error = "No text content extracted from file"
            logger.warning(f"{filename}: {error}")
            return [], error

        # 2. Chunk text
        chunks = split_text(
            text, chunk_size=config["chunk_size"], overlap=config["chunk_overlap"]
        )
        logger.info(f"  Chunked {filename}: {len(chunks)} chunks")

        # Add metadata to each chunk
        for chunk in chunks:
            chunk["metadata"].update(metadata)
            chunk["metadata"]["source_file"] = filename
            chunk["metadata"].update(extract_path_metadata(filename))
            chunk["metadata"] = enrich_metadata(chunk["metadata"], chunk["text"])

        return chunks, None

    except Exception as e:
        error = f"Failed to process: {e!s}"
        logger.error(f"{filename}: {error}", exc_info=True)
        return [], error


def batch_embed(
    chunks: list[dict],
    batch_size: int,
    max_retries: int = 3,
    embedder: Optional["BatchEmbedder"] = None,
) -> tuple[list[dict], int]:
    """
    Generate embeddings for chunks in batches with retry logic.

    Args:
        chunks: List of chunks with text and metadata
        batch_size: Number of chunks to embed at once
        max_retries: Maximum number of retries for failed batches
        embedder: Pre-created BatchEmbedder instance to reuse. If None, one is
            created and closed internally (legacy behaviour).

    Returns:
        Tuple of (list of chunks with embeddings added, number of failed chunks)
    """
    if not chunks:
        logger.warning("No chunks provided for embedding")
        return [], 0

    _owns_embedder = embedder is None
    if _owns_embedder:
        embedder = BatchEmbedder()

    results = []
    failed_count = 0
    total_batches = (len(chunks) - 1) // batch_size + 1

    for i in range(0, len(chunks), batch_size):
        if _shutdown_requested:
            logger.warning("Shutdown requested, stopping embedding generation")
            break

        batch = chunks[i : i + batch_size]
        batch_num = i // batch_size + 1
        logger.info(
            f"Embedding batch {batch_num}/{total_batches} ({len(batch)} chunks)"
        )

        success = False
        for attempt in range(max_retries):
            try:
                batch_dict = {
                    "text": [c["text"] for c in batch],
                    "metadata": [c["metadata"] for c in batch],
                }

                result = embedder(batch_dict)

                if "vector" not in result or len(result["vector"]) != len(batch):
                    raise ValueError(
                        f"Invalid embedding response: expected {len(batch)} vectors"
                    )

                for j, chunk in enumerate(batch):
                    chunk["vector"] = result["vector"][j]
                    results.append(chunk)

                success = True
                break

            except Exception as e:
                logger.warning(
                    f"Embedding batch {batch_num} failed (attempt {attempt + 1}/{max_retries}): {e}"
                )
                if attempt == max_retries - 1:
                    logger.error(
                        f"Failed to embed batch {batch_num} after {max_retries} attempts"
                    )
                    failed_count += len(batch)

        if not success:
            logger.error(f"Skipping batch {batch_num} ({len(batch)} chunks)")

    if _owns_embedder:
        embedder.close()
    logger.info(f"Embedding complete: {len(results)} successful, {failed_count} failed")
    return results, failed_count


def batch_extract_graph(
    chunks: list[dict],
    batch_size: int,
    max_retries: int = 3,
    extractor: Optional["GraphExtractor"] = None,
) -> tuple[list[dict], int]:
    """
    Extract graph data from chunks in batches with retry logic.

    Args:
        chunks: List of chunks with text and metadata
        batch_size: Number of chunks to process at once
        max_retries: Maximum number of retries for failed batches
        extractor: Pre-created GraphExtractor instance to reuse. If None, one is
            created and closed internally (legacy behaviour).

    Returns:
        Tuple of (list of chunks with graph data added, number of failed chunks)
    """
    if not chunks:
        logger.warning("No chunks provided for graph extraction")
        return [], 0

    _owns_extractor = extractor is None
    if _owns_extractor:
        extractor = GraphExtractor()

    results = []
    failed_count = 0
    total_batches = (len(chunks) - 1) // batch_size + 1

    for i in range(0, len(chunks), batch_size):
        if _shutdown_requested:
            logger.warning("Shutdown requested, stopping graph extraction")
            break

        batch = chunks[i : i + batch_size]
        batch_num = i // batch_size + 1
        logger.info(
            f"Extracting graph batch {batch_num}/{total_batches} ({len(batch)} chunks)"
        )

        success = False
        for attempt in range(max_retries):
            try:
                batch_dict = {
                    "text": [c["text"] for c in batch],
                    "metadata": [c["metadata"] for c in batch],
                }

                result = extractor(batch_dict)

                if "graph_nodes" not in result or "graph_edges" not in result:
                    raise ValueError("Invalid graph extraction response structure")
                if len(result["graph_nodes"]) != len(batch) or len(
                    result["graph_edges"]
                ) != len(batch):
                    raise ValueError(
                        f"Graph response length mismatch: expected {len(batch)}"
                    )

                for j, chunk in enumerate(batch):
                    chunk["graph_nodes"] = result["graph_nodes"][j]
                    chunk["graph_edges"] = result["graph_edges"][j]
                    results.append(chunk)

                success = True
                break

            except Exception as e:
                logger.warning(
                    f"Graph extraction batch {batch_num} failed (attempt {attempt + 1}/{max_retries}): {e}"
                )
                if attempt == max_retries - 1:
                    logger.error(
                        f"Failed to extract graph for batch {batch_num} after {max_retries} attempts"
                    )
                    failed_count += len(batch)

        if not success:
            for chunk in batch:
                chunk["graph_nodes"] = []
                chunk["graph_edges"] = []
                results.append(chunk)
            logger.error(f"Added batch {batch_num} with empty graph data")

    if _owns_extractor:
        extractor.close()
    logger.info(
        f"Graph extraction complete: {len(results) - failed_count} successful, {failed_count} with empty data"
    )
    return results, failed_count


def _iter_file_batches(
    client,
    bucket_name: str,
    prefix: str,
    batch_size: int,
    config: dict[str, Any],
    stats: dict[str, Any],
) -> Iterator[list[tuple[str, bytes]]]:
    """
    Yield fixed-size batches of downloaded PDFs from MinIO.

    Phase 1: List all object names (cheap metadata — no bytes transferred).
    Phase 2: Download each batch in parallel using a thread pool.

    Download failures are counted in stats["files_failed"] and logged but do
    not stop the stream.

    Args:
        client: Minio client instance
        bucket_name: Bucket to list
        prefix: Key prefix filter
        batch_size: Max files per yielded batch
        config: Pipeline config dict (max_workers used for download concurrency)
        stats: Shared stats dict mutated in-place

    Yields:
        List of (object_name, file_bytes) tuples, at most batch_size entries
    """
    # Phase 1: collect all document names (names are small — listing is metadata-only)
    all_doc_names: list[str] = []
    for obj in client.list_objects(bucket_name, prefix=prefix, recursive=True):
        if _shutdown_requested:
            return
        stats["files_seen"] += 1
        ext = (
            ("." + obj.object_name.lower().rsplit(".", 1)[-1])
            if "." in obj.object_name
            else ""
        )
        if ext in SUPPORTED_EXTENSIONS:
            all_doc_names.append(obj.object_name)
        else:
            logger.debug(f"Skipping unsupported file type ({ext}): {obj.object_name}")

    def _download(name: str) -> tuple[str, bytes]:
        resp = client.get_object(bucket_name, name)
        data = resp.read()
        resp.close()
        return name, data

    # Phase 2: download in parallel batches
    max_workers = config["max_workers"]
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for i in range(0, len(all_doc_names), batch_size):
            if _shutdown_requested:
                break
            batch_names = all_doc_names[i : i + batch_size]
            futures = {pool.submit(_download, name): name for name in batch_names}
            batch_results: list[tuple[str, bytes]] = []
            for future in as_completed(futures):
                if _shutdown_requested:
                    break
                name = futures[future]
                try:
                    batch_results.append(future.result())
                    stats["files_downloaded"] += 1
                except Exception as e:
                    logger.error(f"Failed to download {name}: {e}")
                    stats["files_failed"] += 1
            if batch_results:
                yield batch_results


def _process_file_batch(
    file_batch: list[tuple[str, bytes]],
    config: dict[str, Any],
    stats: dict[str, Any],
    qdrant_indexer,
    neo4j_indexer,
    batch_num: int,
    embedder,
    extractor,
) -> None:
    """
    Run the full per-batch pipeline: parse+chunk -> [embed ‖ graph] -> Qdrant + Neo4j.

    Fork A (embed) and Fork B (graph extract) run concurrently in a thread pool.
    Indexers and AI clients are passed in (created once in main, reused across batches).

    Args:
        file_batch: List of (object_name, file_bytes) tuples for this batch
        config: Pipeline configuration dict
        stats: Shared stats dict mutated in-place
        qdrant_indexer: Initialised QdrantIndexer (reused across batches)
        neo4j_indexer: Initialised Neo4jIndexer or None if graph disabled
        batch_num: 1-based batch counter for log messages
        embedder: Shared BatchEmbedder instance
        extractor: Shared GraphExtractor instance or None if graph disabled
    """
    # Stage A: Parse + chunk in parallel
    batch_chunks: list[dict] = []
    with ThreadPoolExecutor(max_workers=config["max_workers"]) as executor:
        futures = [
            executor.submit(process_single_file, fi, config) for fi in file_batch
        ]
        for future in as_completed(futures):
            if _shutdown_requested:
                for f in futures:
                    f.cancel()
                break
            try:
                chunks, error = future.result()
                if chunks:
                    batch_chunks.extend(chunks)
                    stats["files_processed"] += 1
                if error:
                    stats["files_failed"] += 1
            except Exception as e:
                logger.error(
                    f"[Batch {batch_num}] File processing future failed: {e}",
                    exc_info=True,
                )
                stats["files_failed"] += 1

    stats["chunks_created"] += len(batch_chunks)

    if not batch_chunks or _shutdown_requested:
        return

    # Stage B: Parallel fork — embed (port 11436) and graph (port 11433) run concurrently.
    # Dedicated cluster nodes eliminate the resource contention that caused the serial fallback.
    # BatchEmbedder uses asyncio.run() internally — safe inside a thread (own event loop).
    # GraphExtractor uses synchronous httpx.Client — no event loop concern.
    chunks_with_vectors: list = []
    chunks_with_graph: list = []

    with ThreadPoolExecutor(max_workers=2) as fork_pool:
        embed_future = fork_pool.submit(
            batch_embed, batch_chunks, config["embedding_batch_size"], 3, embedder
        )
        graph_future = None
        if config["enable_graph"] and neo4j_indexer and extractor:
            graph_future = fork_pool.submit(
                batch_extract_graph,
                batch_chunks,
                config["graph_batch_size"],
                3,
                extractor,
            )

        try:
            chunks_with_vectors, embed_failures = embed_future.result()
            stats["vectors_failed"] += embed_failures
        except Exception as e:
            logger.error(f"[Batch {batch_num}] Embed fork failed: {e}", exc_info=True)
            stats["vectors_failed"] += len(batch_chunks)

        if graph_future is not None:
            try:
                chunks_with_graph, graph_failures = graph_future.result()
                stats["graph_failed"] += graph_failures
            except Exception as e:
                logger.error(
                    f"[Batch {batch_num}] Graph fork failed: {e}", exc_info=True
                )
                stats["graph_failed"] += len(batch_chunks)

    # Stage D: Index to Qdrant (sub-batches of 100)
    if chunks_with_vectors and not _shutdown_requested:
        for i in range(0, len(chunks_with_vectors), 100):
            if _shutdown_requested:
                break
            sub = chunks_with_vectors[i : i + 100]
            for attempt in range(3):
                try:
                    indexed = qdrant_indexer.write(sub)
                    stats["vectors_indexed"] += indexed
                    break
                except Exception as e:
                    logger.warning(
                        f"[Batch {batch_num}] Qdrant attempt {attempt + 1}/3: {e}"
                    )
                    if attempt == 2:
                        logger.error(
                            f"[Batch {batch_num}] Failed to index sub-batch to Qdrant after 3 attempts"
                        )

    # Stage E: Index graph results to Neo4j
    if chunks_with_graph and not _shutdown_requested:
        for i in range(0, len(chunks_with_graph), 100):
            if _shutdown_requested:
                break
            sub = chunks_with_graph[i : i + 100]
            for attempt in range(3):
                try:
                    indexed = neo4j_indexer.write(sub)
                    stats["graph_indexed"] += indexed
                    break
                except Exception as e:
                    logger.warning(
                        f"[Batch {batch_num}] Neo4j attempt {attempt + 1}/3: {e}"
                    )
                    if attempt == 2:
                        logger.error(
                            f"[Batch {batch_num}] Failed to index sub-batch to Neo4j after 3 attempts"
                        )


def main(
    bucket_name: str,
    prefix: str,
    max_workers: int | None = None,
    enable_graph: bool | None = None,
    file_batch_size: int | None = None,
) -> tuple[int, dict[str, Any]]:
    """
    Main ingestion workflow with production-grade error handling.

    This function orchestrates the complete document ingestion pipeline:
    1. Validates configuration and inputs
    2. Streams documents from MinIO in fixed-size memory batches
    3. Per batch: parses+chunks in parallel, embeds, indexes to Qdrant
    4. Per batch (optional): extracts graph data, indexes to Neo4j

    Args:
        bucket_name: MinIO bucket name (required, non-empty string)
        prefix: Prefix path for files to ingest (required, non-empty string)
        max_workers: Number of parallel workers for file processing (1-32, default from config)
        enable_graph: Whether to extract graph data (slow, optional, default from config)
        file_batch_size: Files processed per memory batch (1-500, default from FILE_BATCH_SIZE env or 20)

    Returns:
        Tuple of (exit_code, stats_dict). Exit code 0 for success, 1 for failure.
        stats_dict keys: files_seen, files_downloaded, files_processed, files_failed,
        chunks_created, vectors_indexed, vectors_failed, graph_indexed, graph_failed.

    Raises:
        ValueError: If required parameters are invalid
        Exception: For critical failures that prevent pipeline execution

    Example:
        >>> exit_code, stats = main("legal-documents", "legal/kenya_law/", max_workers=4)
        >>> print(exit_code, stats["vectors_indexed"])
    """
    # Install signal handlers for graceful shutdown (only valid in main thread)
    import threading

    if threading.current_thread() is threading.main_thread():
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
        return 1, {}

    # Override config with provided arguments
    if max_workers is not None:
        if max_workers < 1 or max_workers > 32:
            raise ValueError(f"max_workers must be between 1 and 32, got {max_workers}")
        config["max_workers"] = max_workers

    if enable_graph is not None:
        config["enable_graph"] = enable_graph

    if file_batch_size is not None:
        if file_batch_size < 1 or file_batch_size > 500:
            raise ValueError(
                f"file_batch_size must be between 1 and 500, got {file_batch_size}"
            )
        config["file_batch_size"] = file_batch_size

    logger.info(f"Starting ingestion: bucket={bucket_name}, prefix={prefix}")
    logger.info(
        f"Configuration: workers={config['max_workers']}, graph={config['enable_graph']}, "
        f"chunk_size={config['chunk_size']}, overlap={config['chunk_overlap']}, "
        f"file_batch_size={config['file_batch_size']}"
    )

    # Statistics tracking
    stats = {
        "files_seen": 0,
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
            secure=config["minio_secure"],
        )

        # Test connection
        if not client.bucket_exists(bucket_name):
            raise ValueError(f"Bucket '{bucket_name}' does not exist")
        logger.info(f"Connected to MinIO bucket: {bucket_name}")

        # 2. Stream files and process in fixed-size memory batches
        logger.info(
            f"Streaming files from MinIO in batches of {config['file_batch_size']}..."
        )
        qdrant_indexer = QdrantIndexer()
        neo4j_indexer = Neo4jIndexer() if config["enable_graph"] else None
        embedder = BatchEmbedder()
        extractor = GraphExtractor() if config["enable_graph"] else None
        batch_num = 0

        try:
            for file_batch in _iter_file_batches(
                client, bucket_name, prefix, config["file_batch_size"], config, stats
            ):
                if _shutdown_requested:
                    break
                batch_num += 1
                logger.info(
                    f"[Batch {batch_num}] {len(file_batch)} files "
                    f"(seen so far: {stats['files_seen']})"
                )
                _process_file_batch(
                    file_batch,
                    config,
                    stats,
                    qdrant_indexer,
                    neo4j_indexer,
                    batch_num,
                    embedder=embedder,
                    extractor=extractor,
                )
                logger.info(
                    f"[Batch {batch_num}] done -- "
                    f"processed={stats['files_processed']} "
                    f"vectors={stats['vectors_indexed']} "
                    f"failed={stats['files_failed']}"
                )
        finally:
            qdrant_indexer.close()
            if neo4j_indexer:
                neo4j_indexer.close()
            embedder.close()
            if extractor:
                extractor.close()

        if batch_num == 0:
            logger.warning("No supported files found under the given prefix.")
            return 0, stats

        # 3. Summary
        print(f"\n{'=' * 60}")
        status = "COMPLETED" if not _shutdown_requested else "INTERRUPTED (graceful)"
        print(f"Ingestion {status}")
        print(f"{'=' * 60}")
        print(f"  Files seen (streamed): {stats['files_seen']}")
        print(f"  Files downloaded:      {stats['files_downloaded']}")
        print(f"  Files processed:       {stats['files_processed']}")
        print(f"  Files failed:          {stats['files_failed']}")
        print(f"  File batches run:      {batch_num}")
        print(f"  Total chunks:          {stats['chunks_created']}")
        print(f"  Vectors indexed:       {stats['vectors_indexed']}")
        print(f"  Vectors failed:        {stats['vectors_failed']}")
        if config["enable_graph"]:
            print(f"  Graph indexed:         {stats['graph_indexed']}")
            print(f"  Graph empty:           {stats['graph_failed']}")
        print(f"{'=' * 60}\n")

        return (0 if stats["files_processed"] > 0 else 1), stats

    except KeyboardInterrupt:
        logger.warning("Received keyboard interrupt, shutting down...")
        return 130, stats  # Standard exit code for SIGINT
    except Exception as e:
        logger.error(f"Fatal error in ingestion pipeline: {e}", exc_info=True)
        return 1, {}


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
  python main.py legal-documents legal/kenya_law/

  # With custom worker count
  python main.py legal-documents legal/kenya_law/ --max-workers 8

  # With graph extraction (slow)
  python main.py legal-documents legal/kenya_law/ --enable-graph

  # Specific year only
  python main.py legal-documents legal/kenya_law/2026/ --max-workers 8 --enable-graph

Environment Variables:
  See .env.example for all available configuration options.
  CLI arguments override environment variables.
        """,
    )

    parser.add_argument(
        "bucket_name", type=str, help="MinIO bucket name containing documents to ingest"
    )

    parser.add_argument(
        "prefix",
        type=str,
        help="Prefix path for files to ingest (e.g., 'kenya_law_data/case')",
    )

    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="Number of parallel workers for file processing (1-32, default: from config)",
    )

    parser.add_argument(
        "--enable-graph",
        action="store_true",
        default=None,
        help="Enable graph extraction (slow, default: from config)",
    )

    parser.add_argument(
        "--file-batch-size",
        type=int,
        default=None,
        help="Files per memory batch (1-500, default: FILE_BATCH_SIZE env var or 20)",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=os.getenv("LOG_LEVEL", "INFO"),
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    # Set log level
    logging.getLogger().setLevel(args.log_level)

    # Run pipeline
    try:
        exit_code, _ = main(
            bucket_name=args.bucket_name,
            prefix=args.prefix,
            max_workers=args.max_workers,
            enable_graph=args.enable_graph,
            file_batch_size=args.file_batch_size,
        )
        sys.exit(exit_code)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)
