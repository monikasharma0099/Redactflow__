"""merge_detections tests (SPEC 1.1)."""

from app.models.schemas import BoundingBox, PIIDetection
from app.services.pii_detector import merge_detections


def _det(text, x, conf, source="regex"):
    return PIIDetection(
        id=f"id-{text}-{x}-{conf}",
        pii_type="email",
        text=text,
        bounding_box=BoundingBox(x=x, y=0, width=50, height=10),
        confidence=conf,
        source=source,
    )


def test_same_text_two_locations_kept():
    dets = [_det("a@b.com", 0, 0.9), _det("a@b.com", 200, 0.9)]
    merged = merge_detections(dets)
    assert len(merged) == 2  # different locations = separate detections


def test_same_span_dedup_keeps_higher_confidence():
    dets = [_det("a@b.com", 10, 0.70, "spacy"), _det("a@b.com", 10, 0.95, "regex")]
    merged = merge_detections(dets)
    assert len(merged) == 1
    assert merged[0].confidence == 0.95
    assert merged[0].source == "regex"


def test_case_insensitive_text_key():
    dets = [_det("A@B.com", 10, 0.9), _det("a@b.com", 10, 0.8)]
    assert len(merge_detections(dets)) == 1


def test_none_bbox_dedup():
    d1 = PIIDetection(id="1", pii_type="name", text="Rahul", bounding_box=None,
                      confidence=0.8, source="spacy")
    d2 = PIIDetection(id="2", pii_type="name", text="Rahul", bounding_box=None,
                      confidence=0.6, source="llm")
    merged = merge_detections([d1, d2])
    assert len(merged) == 1 and merged[0].confidence == 0.8
