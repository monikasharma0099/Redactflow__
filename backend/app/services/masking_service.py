"""Image masking service (SPEC 1.5).

Styles: blur, pixelate, blackbox, redbox (proper semi-transparent RGBA
composite), whitebox, synthetic (Faker replacement text scaled to fit the
bbox). Detections with bounding_box=None are never masked (no fabricated
boxes). Label drawing clamps y so text never renders off-image.
"""

import logging
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from app.models.schemas import PIIDetection
from app.services.synthetic_service import SyntheticDataService, get_synthetic_service

logger = logging.getLogger(__name__)

MASK_STYLES = {"blur", "pixelate", "blackbox", "redbox", "whitebox", "synthetic"}

_PADDING = 2


def _clamp_box(img_w: int, img_h: int, x: int, y: int, w: int, h: int) -> Tuple[int, int, int, int]:
    x0 = max(0, x - _PADDING)
    y0 = max(0, y - _PADDING)
    x1 = min(img_w, x + w + _PADDING)
    y1 = min(img_h, y + h + _PADDING)
    return x0, y0, max(1, x1 - x0), max(1, y1 - y0)


class MaskingService:
    """Apply visual masking effects to images."""

    def __init__(self, synthetic: Optional[SyntheticDataService] = None):
        self.synthetic = synthetic or get_synthetic_service()

    # -- public -----------------------------------------------------------------
    def apply_mask(
        self,
        image: Image.Image,
        detections: List[PIIDetection],
        mask_type: str = "blur",
    ) -> Image.Image:
        """Mask every detection that has a real bounding box."""
        if mask_type not in MASK_STYLES:
            logger.warning("Unknown mask type %r — falling back to blackbox", mask_type)
            mask_type = "blackbox"

        result = image.convert("RGB")
        boxes = [d for d in detections if d.bounding_box is not None]

        if mask_type == "synthetic":
            return self._apply_synthetic(result, boxes)

        for det in boxes:
            b = det.bounding_box
            x, y, w, h = _clamp_box(result.width, result.height, b.x, b.y, b.width, b.height)
            if mask_type == "blur":
                result = self._blur(result, x, y, w, h)
            elif mask_type == "pixelate":
                result = self._pixelate(result, x, y, w, h)
            elif mask_type == "blackbox":
                ImageDraw.Draw(result).rectangle([x, y, x + w, y + h], fill=(0, 0, 0))
            elif mask_type == "whitebox":
                ImageDraw.Draw(result).rectangle([x, y, x + w, y + h], fill=(255, 255, 255))
            elif mask_type == "redbox":
                result = self._redbox(result, x, y, w, h)
        return result

    # -- styles ------------------------------------------------------------------
    def _blur(self, image: Image.Image, x: int, y: int, w: int, h: int) -> Image.Image:
        region = image.crop((x, y, x + w, y + h))
        blurred = region.filter(ImageFilter.GaussianBlur(radius=max(6, min(w, h) // 3)))
        image.paste(blurred, (x, y))
        return image

    def _pixelate(self, image: Image.Image, x: int, y: int, w: int, h: int,
                  pixel_size: int = 8) -> Image.Image:
        region = image.crop((x, y, x + w, y + h))
        small = region.resize(
            (max(1, w // pixel_size), max(1, h // pixel_size)), Image.Resampling.NEAREST
        )
        image.paste(small.resize((w, h), Image.Resampling.NEAREST), (x, y))
        return image

    def _redbox(self, image: Image.Image, x: int, y: int, w: int, h: int) -> Image.Image:
        """Proper semi-transparent red box via RGBA alpha compositing."""
        base = image.convert("RGBA")
        overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
        ImageDraw.Draw(overlay).rectangle([x, y, x + w, y + h], fill=(200, 40, 40, 178))
        return Image.alpha_composite(base, overlay).convert("RGB")

    def _apply_synthetic(self, image: Image.Image,
                         detections: List[PIIDetection]) -> Image.Image:
        """White-out the PII and draw a format-preserving replacement scaled
        to fit inside the bbox (font shrunk until the text fits)."""
        result = image.copy()
        draw = ImageDraw.Draw(result)
        for det in detections:
            replacement = self.synthetic.generate(det.pii_type, det.text)
            det.masked_text = replacement
            b = det.bounding_box
            x, y, w, h = _clamp_box(result.width, result.height, b.x, b.y, b.width, b.height)
            draw.rectangle([x, y, x + w, y + h], fill=(255, 255, 255))
            font, fitted = self._fit_text(draw, replacement, w, h)
            tx, ty = self._clamped_text_origin(x, y, h, draw, fitted, font)
            draw.text((tx, ty), fitted, fill=(40, 40, 40), font=font)
        return result

    # -- text fitting -------------------------------------------------------------
    @staticmethod
    def _fit_text(draw: ImageDraw.ImageDraw, text: str, box_w: int, box_h: int):
        """Return (font, text) guaranteed to fit the box width: shrink the
        font first, then truncate with an ellipsis as a last resort."""
        font = MaskingService._font_fitting(draw, text, box_w, box_h)
        if draw.textlength(text, font=font) <= box_w - 4:
            return font, text
        while len(text) > 1:
            text = text[:-2] + "…"
            if draw.textlength(text, font=font) <= box_w - 4:
                break
        return font, text

    @staticmethod
    def _font_fitting(draw: ImageDraw.ImageDraw, text: str,
                      box_w: int, box_h: int) -> ImageFont.ImageFont:
        """Shrink the font until the text fits the box (PIL font metrics)."""
        try:
            size = max(4, min(box_h - 2, 32))
            while size >= 4:
                font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size
                )
                if draw.textlength(text, font=font) <= box_w - 4:
                    return font
                size -= 1
        except OSError:
            pass
        return ImageFont.load_default()

    @staticmethod
    def _clamped_text_origin(x: int, y: int, h: int, draw: ImageDraw.ImageDraw,
                             text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
        """Clamp the y origin so the label never renders off-image."""
        try:
            _, top, _, bottom = font.getbbox(text)
            text_h = max(1, bottom - top)
        except Exception:
            top, text_h = 0, max(1, h - 2)
        ty = y + max(0, (h - text_h) // 2) - top
        ty = max(0, min(ty, max(0, y + h - text_h)))
        return x + 2, ty

    # -- preview overlay ------------------------------------------------------------
    def add_detection_overlay(self, image: Image.Image,
                              detections: List[PIIDetection]) -> Image.Image:
        """Draw labeled boxes for preview; labels clamped to stay on-image."""
        result = image.convert("RGB").copy()
        draw = ImageDraw.Draw(result)
        palette = [
            (255, 100, 100), (100, 255, 100), (100, 100, 255), (255, 200, 100),
            (255, 100, 255), (100, 255, 255), (200, 100, 255), (255, 255, 100),
        ]
        for i, det in enumerate(d for d in detections if d.bounding_box is not None):
            color = palette[i % len(palette)]
            b = det.bounding_box
            draw.rectangle([b.x, b.y, b.x + b.width, b.y + b.height], outline=color, width=2)
            label = f"{det.pii_type.upper()} ({det.confidence:.2f})"
            label_w = int(draw.textlength(label)) + 4
            ly = b.y - 14 if b.y - 14 >= 0 else min(b.y + b.height + 1, result.height - 14)
            ly = max(0, ly)
            draw.rectangle([b.x, ly, b.x + label_w, ly + 13], fill=color)
            draw.text((b.x + 2, ly + 1), label, fill=(255, 255, 255))
        return result


_service: Optional[MaskingService] = None


def get_masking_service() -> MaskingService:
    """Lazy singleton factory."""
    global _service
    if _service is None:
        _service = MaskingService()
    return _service
