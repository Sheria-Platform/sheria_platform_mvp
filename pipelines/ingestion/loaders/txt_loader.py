# pipelines/ingestion/loaders/txt_loader.py


def parse_txt_bytes(file_bytes: bytes, filename: str) -> tuple[str, dict]:
    """Parse a plain-text file from raw bytes."""
    text = file_bytes.decode("utf-8", errors="replace")
    metadata = {"filename": filename, "type": "txt", "char_count": len(text)}
    return text, metadata
