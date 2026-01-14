import requests
import json
from langchain_ollama import OllamaEmbeddings

# Configuration
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "rag_collection"
QDRANT_URL = f"http://{QDRANT_HOST}:{QDRANT_PORT}"

print(f"✓ Connecting to Qdrant at {QDRANT_URL}")

try:
    resp = requests.get(f"{QDRANT_URL}/collections/{COLLECTION_NAME}")
    if resp.status_code == 200:
        print(f"✓ Collection '{COLLECTION_NAME}' exists")
    else:
        print(f"✗ Collection not found: {resp.status_code}")
        print(f"Available collections:")
        resp = requests.get(f"{QDRANT_URL}/collections")
        collections = resp.json()
        for col in collections['result']['collections']:
            print(f"  - {col['name']}")
        exit()
except Exception as e:
    print(f"Connection error: {e}")
    exit()

# Step 2: Initialize Ollama embeddings
embedder = OllamaEmbeddings(model="nomic-embed-text")
print("✓ Using Ollama embeddings for query")

# Step 3: User query
query_text = "What was the ruling in Paul Theuri Mutahi v Family Bank Limited?"

# Step 4: Generate query vector
query_vector = embedder.embed_query(query_text)
print(f"✓ Generated query vector with {len(query_vector)} dimensions")

# Step 5: Search using REST API
try:
    search_payload = {
        "vector": query_vector,
        "limit": 5,
        "with_payload": True
    }
    
    resp = requests.post(
        f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points/search",
        json=search_payload
    )
    
    if resp.status_code == 200:
        results = resp.json()
        
        if results['result']:
            print(f"\n✓ Found {len(results['result'])} results\n")
            for i, hit in enumerate(results['result'], 1):
                payload = hit['payload']
                metadata = payload.get('metadata', {})
                text_snippet = payload.get('text', '')
                score = hit['score']
                
                print(f"{i}. File: {metadata.get('filename', 'N/A')}")
                print(f"   Chunk hash: {metadata.get('chunk_hash', 'N/A')}")
                print(f"   Score: {score:.4f}")
                print(f"   Snippet: {text_snippet[:300]}...\n")
        else:
            print("No results found.")
    else:
        print(f"Search failed with status {resp.status_code}")
        print(f"Response: {resp.text}")
        
except Exception as e:
    print(f"Error: {e}")