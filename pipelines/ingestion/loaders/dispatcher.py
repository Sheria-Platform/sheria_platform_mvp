# pipelines/ingestion/loaders/dispatcher.py
import logging
from typing import Callable, Tuple

from pipelines.ingestion.loaders.pdf_loader import parse_pdf_bytes
from pipelines.ingestion.loaders.docx_loader import parse_docx_bytes
from pipelines.ingestion.loaders.html_loader import parse_html_bytes
from pipelines.ingestion.loaders.txt_loader import parse_txt_bytes

logger = logging.getLogger(__name__)

# All file extensions the pipeline will accept from MinIO
SUPPORTED_EXTENSIONS = frozenset([".pdf", ".docx", ".html", ".htm", ".txt"])

_LOADER_MAP: dict[str, Callable] = {
    ".pdf":  parse_pdf_bytes,
    ".docx": parse_docx_bytes,
    ".html": parse_html_bytes,
    ".htm":  parse_html_bytes,  # alias — same parser
    ".txt":  parse_txt_bytes,
}


def get_loader(filename: str) -> Callable[[bytes, str], Tuple[str, dict]]:
    """
    Return the appropriate loader function for the given filename.

    Args:
        filename: File path or name with extension.

    Returns:
        A callable with signature (file_bytes, filename) -> (text, metadata).

    Raises:
        ValueError: If the file extension is not supported.
    """
    ext = ("." + filename.lower().rsplit(".", 1)[-1]) if "." in filename else ""
    loader = _LOADER_MAP.get(ext)
    if loader is None:
        raise ValueError(
            f"Unsupported file type {ext!r} for {filename!r}. "
            f"Supported: {sorted(SUPPORTED_EXTENSIONS)}"
        )
    return loader
