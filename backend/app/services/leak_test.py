"""Redaction verification / leak test (SPEC 1.6).

`verify_redaction` re-OCRs the masked image and checks whether any of the
originally detected PII strings still appear in the extracted text. It is
used by the test suite and is also runnable as a script:

    python -m app.services.leak_test
"""

import logging
import sys
from dataclasses import dataclass, field
from typing import List, Optional

from PIL import Image

from app.models.schemas import PIIDetection

logger = logging.getLogger(__name__)


@dataclass
class LeakReport:
    total_detections: int
    leaked_count: int
    leaked_texts: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.leaked_count == 0


def _normalize(text: str) -> str:
    """Whitespace/case-insensitive normalization for OCR comparison."""
    return "".join(text.split()).lower()


def verify_redaction(
    original_img: Image.Image,
    masked_img: Image.Image,
    detections: List[PIIDetection],
    ocr_service=None,
) -> LeakReport:
    """Re-OCR the masked image; any surviving PII string is a leak.

    `original_img` is accepted for interface completeness (e.g. future
    pixel-diff heuristics); the leak decision is based on OCR of the
    masked image.
    """
    if ocr_service is None:
        from app.services.ocr_service import get_ocr_service

        ocr_service = get_ocr_service()

    regions = ocr_service.extract_text(masked_img)
    masked_text = _normalize("\n".join(r.get("text", "") for r in regions))

    leaked = [
        det.text
        for det in detections
        if det.text and det.bounding_box is not None and _normalize(det.text) in masked_text
    ]
    report = LeakReport(
        total_detections=sum(1 for d in detections if d.bounding_box is not None),
        leaked_count=len(leaked),
        leaked_texts=leaked,
    )
    if report.passed:
        logger.info("Leak test passed: %d detections verified redacted",
                    report.total_detections)
    else:
        logger.warning("Leak test FAILED: %d/%d PII strings still visible: %s",
                       report.leaked_count, report.total_detections, leaked)
    return report


def _demo() -> int:
    """Script entry point: draw known PII on an image, blackbox-mask it and
    verify no leak. Requires an OCR backend (EasyOCR)."""
    from PIL import ImageDraw, ImageFont

    from app.models.schemas import BoundingBox
    from app.services.masking_service import MaskingService

    text = "Contact rahul.sharma@example.com"
    img = Image.new("RGB", (640, 80), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    except OSError:
        font = ImageFont.load_default()
    draw.text((10, 25), text, fill=(0, 0, 0), font=font)

    detection = PIIDetection(
        id="demo",
        pii_type="email",
        text="rahul.sharma@example.com",
        bounding_box=BoundingBox(x=95, y=25, width=320, height=24),
        confidence=0.95,
        source="regex",
    )
    masked = MaskingService().apply_mask(img, [detection], "blackbox")

    try:
        report = verify_redaction(img, masked, [detection])
    except Exception as exc:
        print(f"OCR backend unavailable ({type(exc).__name__}); cannot run demo.")
        return 2
    print(f"LeakReport: total={report.total_detections} "
          f"leaked={report.leaked_count} passed={report.passed}")
    return 0 if report.passed else 1


if __name__ == "__main__":
    sys.exit(_demo())
