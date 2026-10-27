# pipelines/ingestion/loaders/image_loader.py
"""Image loader: extracts text from scanned documents/photos with Tesseract OCR."""

import io
import logging
import os
from typing import Any

import pytesseract
from PIL import Image, ImageOps

logger = logging.getLogger(__name__)

# Tesseract language codes, e.g. "eng" or "eng+swa". Each code needs its
# traineddata file installed alongside the tesseract binary.
OCR_LANGUAGES = os.getenv("OCR_LANGUAGES", "eng")

# Guards against decompression bombs and runaway multi-frame TIFFs.
MAX_PIXELS = 100_000_000
MAX_FRAMES = 200


def ocr_image(frame: Image.Image) -> tuple[str, list[float]]:
    """OCR one frame; return (text, per-word confidences on a 0-100 scale)."""
    frame = ImageOps.exif_transpose(frame)
    # Tesseract expects greyscale/RGB; palette, CMYK and 16-bit modes confuse it.
    frame = frame.convert("L")

    data = pytesseract.image_to_data(
        frame, lang=OCR_LANGUAGES, output_type=pytesseract.Output.DICT
    )
    # Rebuild text from the single image_to_data pass (avoids OCR'ing twice):
    # words join into lines, lines into paragraphs, paragraphs split by a blank line.
    lines: dict[tuple[int, int, int], list[str]] = {}
    confidences: list[float] = []
    for i, word in enumerate(data["text"]):
        # conf == -1 marks layout rows (block/line), not recognised words.
        if not word.strip() or float(data["conf"][i]) < 0:
            continue
        confidences.append(float(data["conf"][i]))
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)

    out: list[str] = []
    previous_par: tuple[int, int] | None = None
    for (block, par, _line), words in lines.items():
        if previous_par is not None and (block, par) != previous_par:
            out.append("")
        out.append(" ".join(words))
        previous_par = (block, par)
    return "\n".join(out), confidences


def parse_image_bytes(file_bytes: bytes, filename: str) -> tuple[str, dict[str, Any]]:
    """
    Run OCR over an image (PNG/JPEG/TIFF/BMP/WEBP). Multi-page TIFFs are read
    frame by frame.

    Args:
        file_bytes: The raw bytes of the image file.
        filename: Original filename for metadata.

    Returns:
        Tuple of (extracted_text, metadata). ``metadata["ocr_confidence"]`` is
        the mean word confidence (0-100); low values mean the scan should be
        reviewed, since OCR'd legal text may not be verbatim.

    Raises:
        ValueError: If the bytes are not a readable image.
        RuntimeError: If the tesseract binary or a language pack is missing.
    """
    try:
        image = Image.open(io.BytesIO(file_bytes))
        width, height = image.size
    except Exception as e:
        raise ValueError(f"{filename!r} is not a readable image: {e}") from e

    if width * height > MAX_PIXELS:
        raise ValueError(
            f"{filename!r} is {width}x{height}px, above the {MAX_PIXELS:,}px limit"
        )

    pages: list[str] = []
    confidences: list[float] = []
    frame_count = min(getattr(image, "n_frames", 1), MAX_FRAMES)

    try:
        for index in range(frame_count):
            image.seek(index)
            text, frame_conf = ocr_image(image)
            pages.append(text.strip())
            confidences.extend(frame_conf)
    except pytesseract.TesseractNotFoundError as e:
        raise RuntimeError(
            "tesseract binary not found. Install it (macOS: `brew install tesseract`, "
            "Debian/Ubuntu: `apt-get install tesseract-ocr`)."
        ) from e
    except pytesseract.TesseractError as e:
        raise RuntimeError(
            f"Tesseract failed on {filename!r} (languages={OCR_LANGUAGES!r}); "
            f"check the traineddata files are installed: {e}"
        ) from e

    text_content = "\n\n".join(page for page in pages if page)
    mean_conf = round(sum(confidences) / len(confidences), 1) if confidences else 0.0

    metadata = {
        "filename": filename,
        "type": "image",
        "ocr": True,
        "ocr_engine": "tesseract",
        "ocr_languages": OCR_LANGUAGES,
        "ocr_confidence": mean_conf,
        "pages": frame_count,
        "char_count": len(text_content),
    }
    logger.info(
        f"OCR'd {filename}: {len(text_content)} chars, {frame_count} frame(s), "
        f"mean confidence {mean_conf}"
    )
    return text_content, metadata
