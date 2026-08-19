"""Shared test fixtures: isolated DATA_DIR, mocked OCR, offline client.

No network, GPU, EasyOCR, spaCy or Ollama is needed: the OCR service is
replaced with a deterministic fake and spaCy/LLM layers are disabled.
"""

import io
import os
import sys

import pytest
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings  # noqa: E402
from app.core.rate_limit import limiter  # noqa: E402

SAMPLE_TEXT = "Email rahul.sharma@example.com Phone +91 9876543210"
FAKE_REGIONS = [
    {
        "text": SAMPLE_TEXT,
        "confidence": 0.99,
        "bbox": {"x": 10, "y": 20, "width": 400, "height": 30},
    }
]


class FakeOCRService:
    """Deterministic OCR stand-in returning fixed regions."""

    def __init__(self, regions=None):
        self.regions = FAKE_REGIONS if regions is None else regions

    def extract_text(self, image):
        return [dict(r, bbox=dict(r["bbox"])) for r in self.regions]


@pytest.fixture()
def fake_ocr():
    return FakeOCRService()


@pytest.fixture()
def client(tmp_path_factory, monkeypatch, fake_ocr):
    """TestClient with isolated DATA_DIR, mocked OCR, rate limit off."""
    data_dir = tmp_path_factory.mktemp("rf-data")
    monkeypatch.setattr(settings, "DATA_DIR", str(data_dir))
    monkeypatch.setattr(settings, "ENABLE_SPACY", False)
    monkeypatch.setattr(settings, "ENABLE_LLM", False)
    monkeypatch.setattr(settings, "API_KEY", None)
    limiter.enabled = False

    # Batch background worker resolves get_ocr_service lazily from the module.
    import app.services.ocr_service as ocr_module

    monkeypatch.setattr(ocr_module, "get_ocr_service", lambda: fake_ocr)

    import main

    main.app.dependency_overrides[ocr_module.get_ocr_service] = lambda: fake_ocr
    from fastapi.testclient import TestClient

    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()
    limiter.enabled = True


@pytest.fixture()
def sample_png() -> bytes:
    """A valid PNG (magic bytes intact) with the sample text drawn on it."""
    img = Image.new("RGB", (500, 80), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except OSError:
        font = ImageFont.load_default()
    draw.text((10, 25), SAMPLE_TEXT, fill=(0, 0, 0), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture()
def tiny_pdf() -> bytes:
    """A real one-page PDF built with reportlab."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    c.drawString(72, 720, SAMPLE_TEXT)
    c.save()
    return buf.getvalue()


def make_pdf(pages: int) -> bytes:
    from reportlab.lib.pagesizes import LETTER
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    for _ in range(pages):
        c.drawString(72, 720, SAMPLE_TEXT)
        c.showPage()
    c.save()
    return buf.getvalue()
