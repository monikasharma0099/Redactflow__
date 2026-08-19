"""OCR service (EasyOCR) with lazy initialization.

easyocr, cv2 and numpy are imported INSIDE functions/factories so that
`import main` (and the test suite) works with none of them installed and
never downloads model weights at import time. The EasyOCR reader is
created on first use via an lru_cache factory + FastAPI Depends.
"""

import logging
from functools import lru_cache
from typing import Any, Dict, List

from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)


class OCRService:
    """Text extraction with bounding boxes. The EasyOCR reader is built
    lazily on first `extract_text` call (model weights download happens
    only then, inside a threadpool-called endpoint)."""

    def __init__(self) -> None:
        self._reader = None

    def _get_reader(self):
        if self._reader is None:
            import easyocr  # lazy import — heavy optional dependency

            logger.info("Initializing EasyOCR languages=%s gpu=%s",
                        settings.OCR_LANGUAGES, settings.OCR_GPU)
            self._reader = easyocr.Reader(
                settings.OCR_LANGUAGES, gpu=settings.OCR_GPU, verbose=False
            )
        return self._reader

    def preprocess(self, image: Image.Image):
        """Contrast/sharpness enhancement + denoise (lazy cv2/numpy import)."""
        import cv2
        import numpy as np
        from PIL import ImageEnhance

        if image.mode != "RGB":
            image = image.convert("RGB")
        image = ImageEnhance.Contrast(image).enhance(1.5)
        image = ImageEnhance.Sharpness(image).enhance(2.0)
        arr = np.array(image)
        return cv2.fastNlMeansDenoisingColored(arr, None, 10, 10, 7, 21)

    def extract_text(self, image: Image.Image) -> List[Dict[str, Any]]:
        """Return regions: {"text", "confidence", "bbox": {x,y,width,height}}."""
        import numpy as np  # noqa: F401  (lazy; used by reader pipeline)

        reader = self._get_reader()
        processed = self.preprocess(image)
        results = reader.readtext(processed)
        regions: List[Dict[str, Any]] = []
        for bbox, text, conf in results:
            xs = [p[0] for p in bbox]
            ys = [p[1] for p in bbox]
            x_min, x_max = int(min(xs)), int(max(xs))
            y_min, y_max = int(min(ys)), int(max(ys))
            regions.append(
                {
                    "text": text.strip(),
                    "confidence": float(conf),
                    "bbox": {
                        "x": x_min,
                        "y": y_min,
                        "width": x_max - x_min,
                        "height": y_max - y_min,
                    },
                }
            )
        logger.info("OCR extracted %d text regions", len(regions))
        return regions


@lru_cache(maxsize=1)
def get_ocr_service() -> OCRService:
    """Lazy singleton factory for FastAPI Depends."""
    return OCRService()
