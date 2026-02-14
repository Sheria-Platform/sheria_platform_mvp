# pipelines/ingestion/loaders/pdf_loader.py
import io
import logging
import tempfile
from typing import Any

try:
    import pypdf
    USE_PYPDF = True
except ImportError:
    from unstructured.partition.pdf import partition_pdf
    USE_PYPDF = False

logger = logging.getLogger(__name__)


def parse_pdf_bytes(file_bytes: bytes, filename: str) -> tuple[str, dict[str, Any]]:
    """
    Parses a PDF file stream using a temporary file for memory efficiency.
    Extracts text and attempts to preserve table structure via HTML metadata.

    Args:
        file_bytes: The raw bytes of the PDF file.
        filename: Original filename for metadata.

    Returns:
        Tuple containing (extracted_text_content, metadata_dict)
    """
    # Use fast PyPDF parser if available (much faster than unstructured)
    if USE_PYPDF:
        try:
            pdf_reader = pypdf.PdfReader(io.BytesIO(file_bytes))
            text_content = ""

            for page_num, page in enumerate(pdf_reader.pages):
                text_content += page.extract_text() + "\n"

            metadata = {
                "filename": filename,
                "type": "pdf",
                "pages": len(pdf_reader.pages),
                "has_tables": False,  # PyPDF doesn't detect tables
                "table_count": 0,
            }

            logger.info(f"Parsed {filename} with PyPDF: {len(text_content)} chars, {len(pdf_reader.pages)} pages")
            return text_content, metadata

        except Exception as e:
            logger.warning(f"PyPDF failed for {filename}, falling back to unstructured: {e}")
            # Fall through to unstructured parsing

    # Fallback to unstructured (slower but more robust)
    text_content = ""
    tables = []

    # Use a temporary file on disk (EBS/Ephemeral storage)
    # instead of processing entirely in RAM (BytesIO).
    # This is critical for preventing OOM kills on K8s workers with large PDFs.
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp_file:
        try:
            # 1. Write bytes to disk
            tmp_file.write(file_bytes)
            tmp_file.flush()  # Ensure data is written before reading

            # 2. Partition PDF
            # strategy="fast" uses simple text extraction without loading models
            # This avoids loading Detectron2 model weights locally
            # 'filename' arg allows unstructured to lazy-load chunks from disk.
            elements = partition_pdf(
                filename=tmp_file.name,
                strategy="fast",
                include_page_breaks=True,
                infer_table_structure=False,  # Fast strategy doesn't support table inference
            )

            # 3. Process Elements
            for el in elements:
                # Append text representation
                text_content += str(el) + "\n"

                # Check for Table elements to extract structural metadata
                if el.category == "Table":
                    # Save HTML representation for potential UI rendering later
                    if hasattr(el.metadata, "text_as_html"):
                        tables.append(el.metadata.text_as_html)

        except Exception as e:
            logger.error(f"Failed to parse PDF {filename}: {str(e)}")
            # In production, you might raise a specific ParseError here
            raise e

    # 4. Construct Metadata
    metadata = {
        "filename": filename,
        "type": "pdf",
        "has_tables": len(tables) > 0,
        "table_count": len(tables),
    }

    return text_content, metadata
