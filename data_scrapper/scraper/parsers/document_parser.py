"""Document metadata extraction and MinIO path building."""

import json
import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class DocumentMetadata:
    source_url: str
    sha256: str
    file_size: int
    doc_type: str                          # e.g. "pdf", "docx"
    jurisdiction: str = "Kenya"
    download_date: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    title: Optional[str] = None
    court: Optional[str] = None
    year: Optional[str] = None
    case_name: Optional[str] = None
    case_number: Optional[str] = None
    source: str = "unknown"                # e.g. "kenya_law", "generic"


def _slugify(text: str) -> str:
    """Convert arbitrary text to a safe filename segment."""
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text[:80]  # cap length


def build_minio_path(meta: DocumentMetadata, filename: str) -> str:
    """
    Build an organised MinIO object key.

    Pattern: legal/{source}/{year}/{case_slug}/{filename}
    Example: legal/kenya_law/2024/republic_v_kamau/judgment.pdf
    """
    year = meta.year or "undated"
    source = _slugify(meta.source)
    case_slug = _slugify(meta.case_name or meta.title or "document")
    safe_filename = _slugify(filename.rsplit(".", 1)[0]) + f".{meta.doc_type}"
    return f"legal/{source}/{year}/{case_slug}/{safe_filename}"


def build_metadata_json(meta: DocumentMetadata) -> dict:
    """Return a JSON-serialisable dict of the document metadata."""
    return asdict(meta)


def serialize_metadata(meta: DocumentMetadata) -> str:
    """Return metadata as a JSON string (for storage as .meta.json)."""
    return json.dumps(build_metadata_json(meta), indent=2)
