import io
import shutil

import pytest
from PIL import Image, ImageDraw, ImageFont

from pipelines.ingestion.loaders.dispatcher import SUPPORTED_EXTENSIONS, get_loader
from pipelines.ingestion.loaders.image_loader import parse_image_bytes

pytestmark = pytest.mark.skipif(
    shutil.which("tesseract") is None, reason="tesseract binary not installed"
)


def _render(text: str, fmt: str = "PNG", size=(900, 200)) -> bytes:
    image = Image.new("RGB", size, "white")
    ImageDraw.Draw(image).text(
        (20, 60), text, fill="black", font=ImageFont.load_default(size=40)
    )
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return buf.getvalue()


@pytest.mark.parametrize("ext, fmt", [(".png", "PNG"), (".jpg", "JPEG"), (".tiff", "TIFF")])
def test_dispatcher_ocrs_supported_image_types(ext, fmt):
    loader = get_loader(f"order{ext}")
    text, meta = loader(_render("Republic versus Kamau", fmt), f"order{ext}")

    assert "Republic" in text
    assert "Kamau" in text
    assert meta["type"] == "image"
    assert meta["ocr"] is True
    assert 0 < meta["ocr_confidence"] <= 100


def test_blank_image_returns_empty_text():
    text, meta = parse_image_bytes(_render("", size=(300, 100)), "blank.png")
    assert text == ""
    assert meta["ocr_confidence"] == 0.0


def test_multiframe_tiff_reads_every_page():
    frames = [Image.open(io.BytesIO(_render(t))) for t in ("First page", "Second page")]
    buf = io.BytesIO()
    frames[0].save(buf, format="TIFF", save_all=True, append_images=frames[1:])

    text, meta = parse_image_bytes(buf.getvalue(), "scan.tiff")

    assert meta["pages"] == 2
    assert "First" in text
    assert "Second" in text


def test_non_image_bytes_raise_value_error():
    with pytest.raises(ValueError, match="not a readable image"):
        parse_image_bytes(b"not an image", "fake.png")


def test_unsupported_extension_still_rejected():
    assert ".gif" not in SUPPORTED_EXTENSIONS
    with pytest.raises(ValueError, match="Unsupported file type"):
        get_loader("anim.gif")
