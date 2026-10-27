# pipelines/ingestion/loaders/pdf_loader.py
import io
import logging
import os
import tempfile
from typing import Any

try:
    import pypdf

    USE_PYPDF = True
except ImportError:
    from unstructured.partition.pdf import partition_pdf

    USE_PYPDF = False

logger = logging.getLogger(__name__)

# A page whose text layer has fewer characters than this is treated as a scan
# and sent to OCR (page numbers/headers alone often leave a few stray chars).
OCR_MIN_PAGE_CHARS = int(os.getenv("OCR_MIN_PAGE_CHARS", "20"))
# Render resolution for OCR; 300 DPI is Tesseract's recommended sweet spot.
OCR_DPI = int(os.getenv("OCR_DPI", "300"))
# Upper bound on OCR'd pages per PDF so a huge scan can't stall a worker.
OCR_MAX_PDF_PAGES = int(os.getenv("OCR_MAX_PDF_PAGES", "100"))


def _ocr_pdf_page(pdf_bytes: bytes, page_index: int) -> tuple[str, list[float]]:
    """
    Render one PDF page and OCR it. Never raises: a page that can't be OCR'd
    (missing tesseract, corrupt page) yields empty text so the rest of the
    document is still ingested.
    """
    # Imported lazily so the PDF loader still works where OCR deps are absent.
    try:
        import pypdfium2

        from pipelines.ingestion.loaders.image_loader import ocr_image

        pdf = pypdfium2.PdfDocument(pdf_bytes)
        try:
            image = pdf[page_index].render(scale=OCR_DPI / 72).to_pil()
        finally:
            pdf.close()
        return ocr_image(image)
    except Exception as e:
        logger.warning(f"OCR failed for PDF page {page_index + 1}: {e}")
        return "", []


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
            ocr_confidences: list[float] = []
            ocr_pages = 0  # pages that yielded text
            ocr_attempts = 0  # pages sent to OCR; this is what the cap bounds
            ocr_skipped_pages = 0

            for page_num, page in enumerate(pdf_reader.pages):
                page_text = page.extract_text() or ""

                # Scanned page: no usable text layer, so fall back to OCR.
                if len(page_text.strip()) < OCR_MIN_PAGE_CHARS:
                    if ocr_attempts < OCR_MAX_PDF_PAGES:
                        ocr_attempts += 1
                        ocr_text, page_conf = _ocr_pdf_page(file_bytes, page_num)
                        if ocr_text.strip():
                            page_text = ocr_text
                            ocr_pages += 1
                            ocr_confidences.extend(page_conf)
                    else:
                        ocr_skipped_pages += 1

                text_content += page_text + "\n"

            metadata = {
                "filename": filename,
                "type": "pdf",
                "pages": len(pdf_reader.pages),
                "has_tables": False,  # PyPDF doesn't detect tables
                "table_count": 0,
                "ocr_pages": ocr_pages,
            }
            if ocr_pages:
                # Mean word confidence 0-100; low values need human review since
                # OCR'd legal text may not be verbatim.
                metadata["ocr_confidence"] = round(
                    sum(ocr_confidences) / len(ocr_confidences), 1
                )
            if ocr_skipped_pages:
                metadata["ocr_skipped_pages"] = ocr_skipped_pages
                logger.warning(
                    f"{filename}: OCR page cap ({OCR_MAX_PDF_PAGES}) reached, "
                    f"{ocr_skipped_pages} scanned page(s) left without text"
                )

            logger.info(
                f"Parsed {filename} with PyPDF: {len(text_content)} chars, "
                f"{len(pdf_reader.pages)} pages, {ocr_pages} OCR'd"
            )
            return text_content, metadata

        except Exception as e:
            logger.warning(
                f"PyPDF failed for {filename}, falling back to unstructured: {e}"
            )
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
            logger.error(f"Failed to parse PDF {filename}: {e!s}")
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
