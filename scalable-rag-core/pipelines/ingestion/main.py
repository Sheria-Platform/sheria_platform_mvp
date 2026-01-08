# pipelines/ingestion/main.py
import ray
from typing import Dict, List
from pipelines.ingestion.embedding.embedding_compute import BatchEmbedder
from pipelines.ingestion.indexing.qdrant_indexing import QdrantIndexer
from pipelines.ingestion.indexing.neo4j_indexing import Neo4jIndexer
from pipelines.ingestion.graph.extractor_graph import GraphExtractor


def main(bucket_name: str, prefix: str, materialize_chunks: bool = True):
    """
    Main Orchestration Flow for RAG ingestion pipeline.
    
    Args:
        bucket_name: S3 bucket containing documents
        prefix: S3 prefix/path to documents
        materialize_chunks: Whether to cache chunked data (avoids recomputation)
    """
    ray.init(ignore_reinit_error=True)
    
    try:
        # 1. Read from S3 using Ray Data (Lazy Loading)
        print(f"Reading files from s3://{bucket_name}/{prefix}")
        ds = ray.data.read_binary_files(
            paths=f"s3://{bucket_name}/{prefix}",
            include_paths=True
        )
        
        # 2. Parse & Chunk (Map Phase)
        print("Parsing and chunking documents...")
        chunked_ds = ds.map_batches(
            process_batch,
            batch_size=10,
            num_cpus=1,
            # Add error handling
            batch_format="pandas"
        )
        
        # Optional: Materialize to avoid recomputation for both branches
        if materialize_chunks:
            print("Materializing chunks (caching for both vector & graph paths)...")
            chunked_ds = chunked_ds.materialize()
        
        # 3. FORK: Branch A - Vector Embeddings (GPU Intensive)
        print("Generating vector embeddings...")
        vector_ds = chunked_ds.map_batches(
            BatchEmbedder,
            concurrency=5,
            # Only allocate GPU if not using Ray Serve
            # num_gpus=0.2,  
            batch_size=100,
            batch_format="pandas"
        )
        
        # 4. FORK: Branch B - Graph Extraction (LLM Intensive)
        print("Extracting knowledge graph entities and relationships...")
        graph_ds = chunked_ds.map_batches(
            GraphExtractor,
            concurrency=10,
            num_gpus=0.5,
            batch_size=5,
            batch_format="pandas"
        )
        
        # 5. Indexing (Write to DBs)
        print("Indexing vectors to Qdrant...")
        vector_ds.write_datasource(QdrantIndexer())
        
        print("Indexing graph to Neo4j...")
        graph_ds.write_datasource(Neo4jIndexer())
        
        print("✓ Ingestion Job Completed Successfully.")
        
    except Exception as e:
        print(f"✗ Ingestion job failed: {str(e)}")
        raise
    finally:
        # Optional: cleanup
        pass

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 3:
        print("Usage: python main.py <bucket_name> <prefix>")
        sys.exit(1)
    
    main(sys.argv[1], sys.argv[2])