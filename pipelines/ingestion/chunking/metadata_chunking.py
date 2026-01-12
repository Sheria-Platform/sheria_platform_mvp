# pipelines/ingestion/chunking/metadata.py
import hashlib
import datetime

def enrich_metadata(base_metadata: dict, content: str) -> dict:
    """Adds hash and timestamp for deduplication and freshness tracking."""
    return {
        **base_metadata,
        "chunk_hash": hashlib.md5(content.encode('utf-8')).hexdigest(),
        "ingested_at": datetime.datetime.now(datetime.UTC).isoformat()
    }
    
if __name__ == "__main__":
    # Example usage
    base_metadata = {"filename": "sample.txt", "type": "text"}
    content = "This is a sample content for metadata enrichment."
    enriched = enrich_metadata(base_metadata, content)
    print(enriched)