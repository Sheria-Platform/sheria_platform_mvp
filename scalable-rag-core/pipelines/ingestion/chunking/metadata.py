# pipelines/ingestion/chunking/metadata.py
import hashlib
import datetime

def enrich_metadata(base_metadata: dict, content: str) -> dict:
    """Adds hash and timestamp for deduplication and freshness tracking."""
    return {
        **base_metadata,
        "chunk_hash": hashlib.md5(content.encode('utf-8')).hexdigest(),
        "ingested_at": datetime.datetime.utcnow().isoformat()
    }