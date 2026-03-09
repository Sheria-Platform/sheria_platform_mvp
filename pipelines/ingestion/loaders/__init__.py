from pipelines.ingestion.loaders.dispatcher import get_loader, SUPPORTED_EXTENSIONS
from pipelines.ingestion.loaders.pdf_loader import parse_pdf_bytes
from pipelines.ingestion.loaders.docx_loader import parse_docx_bytes
from pipelines.ingestion.loaders.html_loader import parse_html_bytes
from pipelines.ingestion.loaders.txt_loader import parse_txt_bytes

__all__ = [
    "get_loader",
    "SUPPORTED_EXTENSIONS",
    "parse_pdf_bytes",
    "parse_docx_bytes",
    "parse_html_bytes",
    "parse_txt_bytes",
]
