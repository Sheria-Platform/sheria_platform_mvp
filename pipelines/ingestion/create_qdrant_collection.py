#!/usr/bin/env python3
"""Create Qdrant collection for Kenya Law Reports"""
import os
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

# Load environment variables
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Configuration
QDRANT_HOST = os.getenv("QDRANT_HOST", "192.168.214.21")
QDRANT_PORT = int(os.getenv("QDRANT_PORT", "6333"))
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "kenya_law_reports")

# Embedding dimension
# NOTE: Must match your embedding model's output dimension
# - nomic-embed-text: 768 dimensions (default)
# - mxbai-embed-large: 1024 dimensions
# - qwen3-embedding:4b: 2560 dimensions
# Check your OLLAMA_EMBED_MODEL and update accordingly
VECTOR_SIZE = int(os.getenv("QDRANT_VECTOR_SIZE", "768"))  # Default for nomic-embed-text

# Connect to Qdrant
client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)

# Check if collection already exists
collections = client.get_collections().collections
existing_names = [col.name for col in collections]

if COLLECTION_NAME in existing_names:
    print(f"⚠️  Collection '{COLLECTION_NAME}' already exists")
    response = input("Delete and recreate? (yes/no): ")
    if response.lower() == "yes":
        client.delete_collection(collection_name=COLLECTION_NAME)
        print(f"✓ Deleted existing collection '{COLLECTION_NAME}'")
    else:
        print("Keeping existing collection. Exiting.")
        exit(0)

# Create collection
print(f"Creating collection '{COLLECTION_NAME}'...")
client.create_collection(
    collection_name=COLLECTION_NAME,
    vectors_config=VectorParams(
        size=VECTOR_SIZE,
        distance=Distance.COSINE  # Cosine similarity for semantic search
    )
)

print(f"✓ Collection '{COLLECTION_NAME}' created successfully!")
print(f"  - Vector size: {VECTOR_SIZE}")
print(f"  - Distance metric: Cosine")
print(f"  - Host: {QDRANT_HOST}:{QDRANT_PORT}")

# Verify creation
info = client.get_collection(collection_name=COLLECTION_NAME)
print("\nCollection info:")
print(f"  - Status: {info.status}")
print(f"  - Points count: {info.points_count if hasattr(info, 'points_count') else 0}")
print(f"  - Vector config: {info.config.params.vectors}")
print("\n✓ Collection is ready for ingestion!")
