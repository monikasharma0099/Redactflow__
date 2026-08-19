"""PDF service: render pages to images at 150 DPI (PyMuPDF, lazy import)."""

import io
import logging
from typing import List

from PIL import Image

from app.core.config import settings

logger = logging.getLogger(__name__)

PDF_DPI = 150


class PDFPageLimitExceeded(Exception):
    """Raised when a PDF exceeds MAX_PDF_PAGES."""


def count_pages(pdf_bytes: bytes) -> int:
    import fitz  # PyMuPDF — lazy import

    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        return doc.page_count


def render_pages(pdf_bytes: bytes, dpi: int = PDF_DPI) -> List[Image.Image]:
    """Render each page to a PIL Image at the given DPI.

    Enforces the MAX_PDF_PAGES cap.
    """
    import fitz  # lazy import

    images: List[Image.Image] = []
    zoom = dpi / 72.0
    matrix = fitz.Matrix(zoom, zoom)
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        if doc.page_count > settings.MAX_PDF_PAGES:
            raise PDFPageLimitExceeded(
                f"PDF has {doc.page_count} pages, limit is {settings.MAX_PDF_PAGES}"
            )
        for page in doc:
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
            images.append(img)
    logger.info("Rendered %d PDF pages at %d DPI", len(images), dpi)
    return images
