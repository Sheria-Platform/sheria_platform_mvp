import io
import shutil

import pypdf
import pytest
from PIL import Image, ImageDraw, ImageFont

from pipelines.ingestion.loaders import image_loader, pdf_loader
from pipelines.ingestion.loaders.pdf_loader import parse_pdf_bytes

pytestmark = pytest.mark.skipif(
    shutil.which("tesseract") is None, reason="tesseract binary not installed"
)


def _scanned_pdf(*page_texts: str) -> bytes:
    """Image-only PDF: no text layer, like a scanned court document."""
    pages = []
    for text in page_texts:
        image = Image.new("RGB", (1200, 300), "white")
        ImageDraw.Draw(image).text(
            (30, 100), text, fill="black", font=ImageFont.load_default(size=60)
        )
        pages.append(image)
    buf = io.BytesIO()
    pages[0].save(buf, format="PDF", save_all=True, append_images=pages[1:], resolution=300)
    return buf.getvalue()


def _text_pdf(text: str) -> bytes:
    """Single-page PDF with a real text layer, hand-built with a valid xref table."""
    stream = f"BT /F1 18 Tf 50 700 Td ({text}) Tj ET".encode()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + body + b"\nendobj\n"
    xref_pos = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += b"trailer\n<< /Root 1 0 R /Size %d >>\n" % (len(objects) + 1)
    return out + b"startxref\n%d\n%%%%EOF\n" % xref_pos


def _merge(*pdfs: bytes) -> bytes:
    writer = pypdf.PdfWriter()
    for data in pdfs:
        for page in pypdf.PdfReader(io.BytesIO(data)).pages:
            writer.add_page(page)
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def test_text_pdf_text_layer_is_used_and_ocr_never_runs(monkeypatch):
    def boom(*_args):
        raise AssertionError("OCR must not run for pages that have a text layer")

    monkeypatch.setattr(pdf_loader, "_ocr_pdf_page", boom)
    pdf = _text_pdf("Republic versus Kamau judgment delivered")
    assert "Republic versus Kamau" in pypdf.PdfReader(io.BytesIO(pdf)).pages[0].extract_text()

    text, meta = parse_pdf_bytes(pdf, "text.pdf")

    assert "Republic versus Kamau" in text
    assert meta["ocr_pages"] == 0
    assert "ocr_confidence" not in meta


def test_scanned_pdf_falls_back_to_ocr():
    text, meta = parse_pdf_bytes(_scanned_pdf("Republic versus Kamau"), "scan.pdf")

    assert "Republic" in text
    assert "Kamau" in text
    assert meta["ocr_pages"] == 1
    assert 0 < meta["ocr_confidence"] <= 100


def test_mixed_pdf_ocrs_only_the_scanned_page():
    pdf = _merge(
        _text_pdf("Typed page with a real text layer"),
        _scanned_pdf("Scanned page two"),
    )

    text, meta = parse_pdf_bytes(pdf, "mixed.pdf")

    assert "real text layer" in text
    assert "Scanned" in text
    assert meta["pages"] == 2
    assert meta["ocr_pages"] == 1


def test_ocr_page_cap_leaves_remaining_pages_unprocessed(monkeypatch):
    monkeypatch.setattr(pdf_loader, "OCR_MAX_PDF_PAGES", 1)

    text, meta = parse_pdf_bytes(_scanned_pdf("First scan", "Second scan"), "big.pdf")

    assert "First" in text
    assert "Second" not in text
    assert meta["ocr_pages"] == 1
    assert meta["ocr_skipped_pages"] == 1


def test_ocr_failure_does_not_fail_the_document(monkeypatch):
    def broken(_image):
        raise RuntimeError("tesseract exploded")

    monkeypatch.setattr(image_loader, "ocr_image", broken)
    pdf = _merge(_text_pdf("Typed page with a real text layer"), _scanned_pdf("Lost scan"))

    text, meta = parse_pdf_bytes(pdf, "partial.pdf")

    assert "real text layer" in text
    assert "Lost" not in text
    assert meta["ocr_pages"] == 0
