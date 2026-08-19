"""Masking service tests (SPEC 1.5)."""

import random

import pytest
from PIL import Image, ImageDraw

from app.models.schemas import BoundingBox, PIIDetection
from app.services.masking_service import MaskingService

BOX = BoundingBox(x=100, y=100, width=120, height=40)


def _noise_image(w=400, h=300, seed=7):
    rng = random.Random(seed)
    img = Image.new("RGB", (w, h))
    img.putdata([(rng.randrange(256), rng.randrange(256), rng.randrange(256))
                 for _ in range(w * h)])
    return img


def _det(box=BOX, pii_type="email", text="user@example.com"):
    return PIIDetection(id="m1", pii_type=pii_type, text=text,
                        bounding_box=box, confidence=0.9, source="regex")


@pytest.fixture()
def svc():
    return MaskingService()


def _crop(img, box=BOX, pad=2):
    return img.crop((box.x - pad, box.y - pad,
                     box.x + box.width + pad, box.y + box.height + pad))


@pytest.mark.parametrize("style", ["blur", "pixelate", "blackbox", "redbox",
                                   "whitebox", "synthetic"])
def test_every_style_modifies_pixels_inside_bbox(svc, style):
    img = _noise_image()
    out = svc.apply_mask(img, [_det()], style)
    assert _crop(out).tobytes() != _crop(img).tobytes()


def test_none_bbox_detection_untouched(svc):
    img = _noise_image()
    det = PIIDetection(id="nb", pii_type="name", text="Rahul",
                       bounding_box=None, confidence=0.8, source="spacy")
    out = svc.apply_mask(img, [det], "blackbox")
    assert out.tobytes() == img.tobytes()  # no fabricated box


def test_redbox_is_semitransparent(svc):
    img = Image.new("RGB", (200, 200), (255, 255, 255))
    out = svc.apply_mask(img, [_det(BoundingBox(x=50, y=50, width=80, height=40))],
                         "redbox")
    r, g, b = out.getpixel((90, 70))
    assert r > 200 and 30 < g < 120 and 30 < b < 120  # red tint, not opaque


def test_synthetic_sets_masked_text(svc):
    det = _det()
    svc.apply_mask(_noise_image(), [det], "synthetic")
    assert det.masked_text and "@" in det.masked_text  # valid email shape


def test_synthetic_text_fits_bbox(svc):
    img = Image.new("RGB", (400, 300), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    box = BoundingBox(x=10, y=10, width=140, height=30)
    long_text = "very.long.email.address@some-company-name.co.in"
    font, fitted = svc._fit_text(draw, long_text, box.width, box.height)
    width = draw.textlength(fitted, font=font)
    assert width <= box.width - 4
    # short text must survive untruncated
    font2, fitted2 = svc._fit_text(draw, "a@b.co", box.width, box.height)
    assert fitted2 == "a@b.co"


def test_overlay_label_clamped_at_top_edge(svc):
    img = _noise_image()
    det = _det(BoundingBox(x=5, y=0, width=60, height=15))
    out = svc.add_detection_overlay(img, [det])  # label would be at y=-14
    assert out.size == img.size  # no crash, label drawn inside
