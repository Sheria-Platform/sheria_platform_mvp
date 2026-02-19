"""
Test connectivity to remote infrastructure.
Run this before executing the ingestion pipeline.
"""
import os
import sys

import httpx
from qdrant_client import QdrantClient
from neo4j import GraphDatabase


def test_ollama_llm():
    """Test Ollama LLM endpoint."""
    endpoint = os.getenv(
        "OLLAMA_LLM_ENDPOINT",
        "http://192.168.214.22:11435/api/chat"
    )
    print(f"\n[1/4] Testing Ollama LLM endpoint: {endpoint}")

    try:
        tags_endpoint = endpoint.replace("/api/chat", "/api/tags")
        response = httpx.get(tags_endpoint, timeout=10.0)
        response.raise_for_status()
        models = response.json().get("models", [])
        print(f"  ✓ Connected. Available models: {len(models)}")
        for model in models[:3]:
            print(f"    - {model.get('name', 'unknown')}")
        return True
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


def test_ollama_embed():
    """Test Ollama embedding endpoint."""
    endpoint = os.getenv(
        "OLLAMA_EMBED_ENDPOINT",
        "http://192.168.214.22:11436/api/embeddings"
    )
    print(f"\n[2/4] Testing Ollama embedding endpoint: {endpoint}")

    try:
        tags_endpoint = endpoint.replace("/api/embeddings", "/api/tags")
        response = httpx.get(tags_endpoint, timeout=10.0)
        response.raise_for_status()
        models = response.json().get("models", [])
        print(f"  ✓ Connected. Available models: {len(models)}")
        for model in models[:3]:
            print(f"    - {model.get('name', 'unknown')}")
        return True
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


def test_qdrant():
    """Test Qdrant connection."""
    host = os.getenv("QDRANT_HOST", "192.168.214.21")
    port = int(os.getenv("QDRANT_PORT", "6333"))
    print(f"\n[3/4] Testing Qdrant: {host}:{port}")

    try:
        client = QdrantClient(host=host, port=port)
        collections = client.get_collections()
        print(f"  ✓ Connected. Collections: {len(collections.collections)}")
        for col in collections.collections[:3]:
            print(f"    - {col.name}")
        return True
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


def test_neo4j():
    """Test Neo4j connection."""
    uri = os.getenv("NEO4J_URI", "bolt://192.168.214.21:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")
    print(f"\n[4/4] Testing Neo4j: {uri}")

    try:
        driver = GraphDatabase.driver(uri, auth=(user, password))
        with driver.session() as session:
            result = session.run("RETURN 1 AS test")
            record = result.single()
            if record["test"] == 1:
                print("  ✓ Connected successfully")
                driver.close()
                return True
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


def main():
    """Run all connectivity tests."""
    print("=" * 60)
    print("Testing Remote Infrastructure Connectivity")
    print("=" * 60)

    results = []
    results.append(("Ollama LLM", test_ollama_llm()))
    results.append(("Ollama Embed", test_ollama_embed()))
    results.append(("Qdrant", test_qdrant()))
    results.append(("Neo4j", test_neo4j()))

    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{name:20} {status}")

    all_passed = all(result[1] for result in results)

    if all_passed:
        print("\n✓ All tests passed! Ready to run ingestion pipeline.")
        sys.exit(0)
    else:
        print("\n✗ Some tests failed. Check your configuration.")
        sys.exit(1)


if __name__ == "__main__":
    main()
