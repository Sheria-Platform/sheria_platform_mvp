"""
Development Data Ingestion Pipeline
Loads files from MinIO and processes them through the RAG pipeline
Simplified version for local development without Ray
"""

import asyncio
import hashlib
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from minio import Minio
from minio.error import S3Error

ENV = os.getenv("ENV", "dev")

class DevConfig:
    """Development environment configuration"""
    # MinIO (S3-compatible storage)
    MINIO_ENDPOINT = "localhost:9000"
    MINIO_ACCESS_KEY = "minioadmin"
    MINIO_SECRET_KEY = "minioadmin"
    MINIO_SECURE = False
    BUCKET_NAME = "kenya-law-data"
    
    # Databases
    QDRANT_HOST = "localhost"
    QDRANT_PORT = 6333
    QDRANT_COLLECTION = "rag_collection"
    NEO4J_URI = "bolt://localhost:7687"
    NEO4J_USER = "neo4j"
    NEO4J_PASSWORD = "password"
    
    # Processing
    BATCH_SIZE = 5  # Process 5 files at a time in dev
    CHUNK_SIZE = 512
    CHUNK_OVERLAP = 50
    
    # LLM/Embedding endpoints (if using local models)
    EMBED_ENDPOINT = "http://localhost:8080/embed"
    LLM_ENDPOINT = "http://localhost:8000/v1"


class MinIOHandler:
    """Handles MinIO operations"""
    
    def __init__(self, config: DevConfig):
        self.config = config
        self.client = Minio(
            config.MINIO_ENDPOINT,
            access_key=config.MINIO_ACCESS_KEY,
            secret_key=config.MINIO_SECRET_KEY,
            secure=config.MINIO_SECURE,
        )
        print(f"✓ Connected to MinIO at {config.MINIO_ENDPOINT}")
    
    def list_files(self, prefix: str = "", file_extension: str = None) -> list[str]:
        """List all files in the bucket"""
        try:
            objects = self.client.list_objects(
                self.config.BUCKET_NAME,
                prefix=prefix,
                recursive=True
            )
            
            files = []
            for obj in objects:
                if file_extension is None or obj.object_name.endswith(file_extension):
                    files.append(obj.object_name)
            
            print(f"✓ Found {len(files)} files in bucket")
            return files
        except S3Error as e:
            print(f"✗ Error listing files: {e}")
            return []
    
    def get_file_bytes(self, object_name: str) -> bytes | None:
        """Get file content as bytes"""
        try:
            response = self.client.get_object(
                self.config.BUCKET_NAME,
                object_name
            )
            data = response.read()
            response.close()
            response.release_conn()
            return data
        except S3Error as e:
            print(f"✗ Error reading {object_name}: {e}")
            return None


class DocumentParser:
    """Parses different document types"""
    
    @staticmethod
    def parse_pdf(file_bytes: bytes, filename: str) -> tuple[str, dict]:
        """Parse PDF document"""
        from pipelines.ingestion.loaders.pdf_loader import parse_pdf_bytes
        return parse_pdf_bytes(file_bytes, filename)
    
    @staticmethod
    def parse_docx(file_bytes: bytes, filename: str) -> tuple[str, dict]:
        """Parse DOCX document"""
        from pipelines.ingestion.loaders.docx_loader import parse_docx_bytes
        return parse_docx_bytes(file_bytes, filename)
    
    @staticmethod
    def parse_html(file_bytes: bytes, filename: str) -> tuple[str, dict]:
        """Parse HTML document"""
        from pipelines.ingestion.loaders.html_loader import parse_html_bytes
        return parse_html_bytes(file_bytes, filename)
    
    @staticmethod
    def parse_text(file_bytes: bytes, filename: str) -> tuple[str, dict]:
        """Parse plain text document"""
        try:
            text = file_bytes.decode('utf-8')
            metadata = {
                'filename': filename,
                'type': 'text',
                'char_count': len(text)
            }
            return text, metadata
        except Exception as e:
            raise ValueError(f"Failed to parse text file: {e}")
    
    def parse_document(self, file_bytes: bytes, filename: str) -> tuple[str, dict]:
        """Parse document based on file extension"""
        ext = Path(filename).suffix.lower()
        
        parsers = {
            '.pdf': self.parse_pdf,
            '.docx': self.parse_docx,
            '.html': self.parse_html,
            '.htm': self.parse_html,
            '.txt': self.parse_text,
        }
        
        parser = parsers.get(ext)
        if not parser:
            raise ValueError(f"Unsupported file type: {ext}")
        
        return parser(file_bytes, filename)


class TextChunker:
    """Chunks text into smaller pieces"""
    
    def __init__(self, chunk_size: int = 512, overlap: int = 50):
        self.chunk_size = chunk_size
        self.overlap = overlap
    
    def chunk_text(self, text: str, metadata: dict) -> list[dict]:
        """Split text into chunks with metadata"""
        from pipelines.ingestion.chunking.splitter_chunking import split_text
        
        chunks = split_text(text, self.chunk_size, self.overlap)
        
        # Enrich each chunk with metadata
        enriched_chunks = []
        for chunk in chunks:
            chunk['metadata'].update(metadata)
            chunk['metadata']['chunk_hash'] = hashlib.md5(
                chunk['text'].encode('utf-8')
            ).hexdigest()
            chunk['metadata']['ingested_at'] = datetime.utcnow().isoformat()
            enriched_chunks.append(chunk)
        
        return enriched_chunks


class VectorIndexer:
    """Indexes chunks into Qdrant"""
    
    def __init__(self, config: DevConfig):
        self.config = config
        from qdrant_client import QdrantClient
        from qdrant_client.http import models
        
        self.client = QdrantClient(
            host=config.QDRANT_HOST,
            port=config.QDRANT_PORT
        )
        self.models = models
        print(f"✓ Connected to Qdrant at {config.QDRANT_HOST}:{config.QDRANT_PORT}")

        # DEV embeddings setup
        if ENV == "dev":
            try:
                from langchain_community.embeddings import OllamaEmbeddings
                self.embedder = OllamaEmbeddings(model="nomic-embed-text")
                print("✓ Using Ollama embeddings for DEV")
            except ImportError:
                print("⚠ langchain_community not installed. Using mock embeddings for DEV.")
                self.embedder = None
        else:
            import httpx
            self.client_http = httpx.Client(timeout=30.0)
            self.endpoint = config.EMBED_ENDPOINT
    
    def ensure_collection(self):
        """Create collection if it doesn't exist"""
        collections = self.client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if self.config.QDRANT_COLLECTION not in collection_names:
            self.client.create_collection(
                collection_name=self.config.QDRANT_COLLECTION,
                vectors_config=self.models.VectorParams(
                    size=1024,  # BGE-M3 embedding size
                    distance=self.models.Distance.COSINE
                )
            )
            print(f"✓ Created collection: {self.config.QDRANT_COLLECTION}")
        else:
            print(f"✓ Collection exists: {self.config.QDRANT_COLLECTION}")
    
    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for texts"""
        if ENV == "dev" and self.embedder:
            # Use Ollama embeddings in DEV
            return [self.embedder.embed_query(t) for t in texts]
        elif ENV != "dev":
            # Use HTTP endpoint in prod
            response = self.client_http.post(
                self.endpoint,
                json={"text": texts, "task_type": "document"}
            )
            response.raise_for_status()
            return response.json()["embeddings"]
        else:
            # Fallback to mock embeddings
            print("⚠ Using mock embeddings (replace with real embeddings in production)")
            import random
            return [[random.random() for _ in range(1024)] for _ in texts]
    
    def index_chunks(self, chunks: list[dict]) -> int:
        """Index chunks with embeddings into Qdrant"""
        import uuid
        
        if not chunks:
            return 0
        
        # Extract texts for embedding
        texts = [chunk['text'] for chunk in chunks]
        
        # Generate embeddings
        print(f"  Generating embeddings for {len(texts)} chunks...")
        embeddings = self.embed_texts(texts)
        
        # Create points for Qdrant
        points = []
        for i, chunk in enumerate(chunks):
            point = self.models.PointStruct(
                id=str(uuid.uuid4()),
                vector=embeddings[i],
                payload={
                    'text': chunk['text'],
                    'metadata': chunk['metadata']
                }
            )
            points.append(point)
        
        # Upload to Qdrant
        self.client.upsert(
            collection_name=self.config.QDRANT_COLLECTION,
            points=points
        )
        
        return len(points)


class GraphIndexer:
    """Indexes entities and relationships into Neo4j"""
    
    def __init__(self, config: DevConfig):
        self.config = config
        from neo4j import GraphDatabase
        
        self.driver = GraphDatabase.driver(
            config.NEO4J_URI,
            auth=(config.NEO4J_USER, config.NEO4J_PASSWORD)
        )
        print(f"✓ Connected to Neo4j at {config.NEO4J_URI}")
    
    def extract_entities(self, chunks: list[dict]) -> dict:
        """Extract entities from chunks (simplified for dev)"""
        # In production, this would call your LLM to extract entities
        # For dev, we'll create simple entities based on document metadata
        
        entities = []
        relationships = []
        
        for chunk in chunks:
            metadata = chunk['metadata']
            filename = metadata.get('filename', 'unknown')
            
            # Create document node
            doc_node = {
                'id': filename,
                'type': 'Document',
                'properties': {
                    'name': filename,
                    'type': metadata.get('type', 'unknown'),
                    'ingested_at': metadata.get('ingested_at')
                }
            }
            entities.append(doc_node)
        
        return {
            'entities': entities,
            'relationships': relationships
        }
    
    def index_graph(self, graph_data: dict) -> int:
     """Index entities and relationships into Neo4j"""
     with self.driver.session() as session:
        count = 0

        for entity in graph_data.get('entities', []):
            props = entity.get('properties', {})

            session.run(
                """
                MERGE (n:Document {id: $id})
                SET n.name = $name,
                    n.doc_type = $doc_type,
                    n.ingested_at = $ingested_at
                """,
                id=entity['id'],
                name=props.get('name'),
                doc_type=props.get('type'),
                ingested_at=props.get('ingested_at'),
            )
            count += 1

        # Relationships (safe as-is)
        for rel in graph_data.get('relationships', []):
            session.run(
                """
                MATCH (a:Document {id: $source})
                MATCH (b:Document {id: $target})
                MERGE (a)-[:RELATES {type: $type}]->(b)
                """,
                source=rel['source'],
                target=rel['target'],
                type=rel['type'],
            )
            count += 1

     return count

    def close(self):
        """Close Neo4j connection"""
        self.driver.close()


class DevIngestionPipeline:
    """Main ingestion pipeline for development"""
    
    def __init__(self):
        self.config = DevConfig()
        self.minio = MinIOHandler(self.config)
        self.parser = DocumentParser()
        self.chunker = TextChunker(
            chunk_size=self.config.CHUNK_SIZE,
            overlap=self.config.CHUNK_OVERLAP
        )
        self.vector_indexer = VectorIndexer(self.config)
        self.graph_indexer = GraphIndexer(self.config)
    
    def process_file(self, filename: str) -> dict:
        """Process a single file through the pipeline"""
        result = {
            'filename': filename,
            'status': 'pending',
            'chunks': 0,
            'vectors': 0,
            'entities': 0,
            'error': None
        }
        
        try:
            # Step 1: Download from MinIO
            print(f"\n📄 Processing: {filename}")
            file_bytes = self.minio.get_file_bytes(filename)
            
            if not file_bytes:
                result['status'] = 'error'
                result['error'] = 'Failed to download file'
                return result
            
            # Step 2: Parse document
            print(f"  Parsing document...")
            text, metadata = self.parser.parse_document(file_bytes, filename)
            
            # Step 3: Chunk text
            print(f"  Chunking text...")
            chunks = self.chunker.chunk_text(text, metadata)
            result['chunks'] = len(chunks)
            
            # Step 4: Index into Qdrant
            print(f"  Indexing {len(chunks)} chunks into Qdrant...")
            vectors_indexed = self.vector_indexer.index_chunks(chunks)
            result['vectors'] = vectors_indexed
            
            # Step 5: Extract and index graph
            print(f"  Extracting entities...")
            graph_data = self.graph_indexer.extract_entities(chunks)
            entities_indexed = self.graph_indexer.index_graph(graph_data)
            result['entities'] = entities_indexed
            
            result['status'] = 'success'
            print(f"  ✓ Successfully processed {filename}")
            
        except Exception as e:
            result['status'] = 'error'
            result['error'] = str(e)
            print(f"  ✗ Error processing {filename}: {e}")
        
        return result
    
    def run(self, file_pattern: str = None, limit: int = None):
        """Run the ingestion pipeline"""
        print("=" * 70)
        print("DEV INGESTION PIPELINE - Kenya Law Data")
        print("=" * 70)
        
        # Setup
        print("\n[1/5] Setting up...")
        self.vector_indexer.ensure_collection()
        
        # List files
        print("\n[2/5] Listing files from MinIO...")
        if file_pattern:
            files = self.minio.list_files(file_extension=file_pattern)
        else:
            files = self.minio.list_files()
        
        if not files:
            print("✗ No files found in bucket")
            return
        
        # Limit files for dev
        if limit:
            files = files[:limit]
            print(f"  Limiting to first {limit} files for development")
        
        # Process files
        print(f"\n[3/5] Processing {len(files)} files...")
        results = []
        
        for i, filename in enumerate(files, 1):
            print(f"\n[{i}/{len(files)}]", end=" ")
            result = self.process_file(filename)
            results.append(result)
        
        # Summary
        print("\n" + "=" * 70)
        print("[4/5] PROCESSING SUMMARY")
        print("=" * 70)
        
        total_files = len(results)
        successful = sum(1 for r in results if r['status'] == 'success')
        failed = sum(1 for r in results if r['status'] == 'error')
        total_chunks = sum(r['chunks'] for r in results)
        total_vectors = sum(r['vectors'] for r in results)
        total_entities = sum(r['entities'] for r in results)
        
        print(f"Total files processed: {total_files}")
        print(f"  ✓ Successful: {successful}")
        print(f"  ✗ Failed: {failed}")
        print(f"\nData indexed:")
        print(f"  Chunks created: {total_chunks}")
        print(f"  Vectors indexed: {total_vectors}")
        print(f"  Graph entities: {total_entities}")
        
        # Show errors
        if failed > 0:
            print(f"\n❌ Errors:")
            for r in results:
                if r['status'] == 'error':
                    print(f"  - {r['filename']}: {r['error']}")
        
        print("\n[5/5] Cleanup...")
        self.graph_indexer.close()
        
        print("\n" + "=" * 70)
        print("✓ PIPELINE COMPLETE")
        print("=" * 70)


def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description='Development ingestion pipeline for Kenya Law data'
    )
    parser.add_argument(
        '--pattern',
        type=str,
        help='File pattern to filter (e.g., .pdf, .docx)',
        default=None
    )
    parser.add_argument(
        '--limit',
        type=int,
        help='Limit number of files to process (for testing)',
        default=None
    )
    
    args = parser.parse_args()
    
    # Run pipeline
    pipeline = DevIngestionPipeline()
    pipeline.run(file_pattern=args.pattern, limit=args.limit)


if __name__ == "__main__":
    main()
