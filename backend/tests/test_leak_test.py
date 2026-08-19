"""Leak-test unit tests (SPEC 1.6) with a mocked OCR backend."""

from PIL import Image

from app.models.schemas import BoundingBox, PIIDetection
from app.services.leak_test import verify_redaction
from app.services.masking_service import MaskingService

TEXT = "rahul.sharma@example.com"


class _OCRSeesNothing:
    def extract_text(self, image):
        return [{"text": "Contact", "bbox": {"x": 0, "y": 0, "width": 10, "height": 10}}]


class _OCRSeesPII:
    def extract_text(self, image):
        return [{"text": f"Contact {TEXT}", "bbox": {"x": 0, "y": 0, "width": 10, "height": 10}}]


def _detection():
    return PIIDetection(
        id="lk1", pii_type="email", text=TEXT,
        bounding_box=BoundingBox(x=50, y=20, width=200, height=25),
        confidence=0.95, source="regex",
    )


def test_blackbox_redaction_passes_verification():
    img = Image.new("RGB", (400, 80), (255, 255, 255))
    det = _detection()
    masked = MaskingService().apply_mask(img, [det], "blackbox")
    report = verify_redaction(img, masked, [det], ocr_service=_OCRSeesNothing())
    assert report.passed
    assert report.leaked_count == 0
    assert report.total_detections == 1


def test_surviving_pii_is_reported_as_leak():
    img = Image.new("RGB", (400, 80), (255, 255, 255))
    det = _detection()
    report = verify_redaction(img, img, [det], ocr_service=_OCRSeesPII())
    assert not report.passed
    assert report.leaked_texts == [TEXT]


def test_unmasked_detection_excluded_from_report():
    img = Image.new("RGB", (400, 80), (255, 255, 255))
    det = PIIDetection(id="nb", pii_type="name", text="Rahul",
                       bounding_box=None, confidence=0.8, source="spacy")
    report = verify_redaction(img, img, [det], ocr_service=_OCRSeesNothing())
    assert report.total_detections == 0 and report.passed
