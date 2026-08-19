"""Bounding-box math tests (SPEC 1.1): proportional interpolation and
the unlocatable-span -> bbox=None rule."""

from app.services.pii_detector import PIIDetector


def _detector():
    return PIIDetector(enable_spacy=False, enable_llm=False)


def test_proportional_interpolation():
    # Region: 10 chars wide text over a 200px wide bbox at x=100.
    regions = [{"text": "0123456789",
                "bbox": {"x": 100, "y": 50, "width": 200, "height": 40}}]
    det = _detector()
    bbox = det._bbox_for_span(2, 6, regions, [0])
    assert bbox is not None
    assert bbox.x == 100 + int(0.2 * 200)   # 140
    assert bbox.width == int(0.4 * 200)      # 80
    assert bbox.y == 50
    assert bbox.height == 40


def test_bbox_inside_owning_region_only():
    regions = [
        {"text": "aaaa", "bbox": {"x": 0, "y": 0, "width": 40, "height": 10}},
        {"text": "bbbb", "bbox": {"x": 0, "y": 20, "width": 40, "height": 10}},
    ]
    det = _detector()
    # span [4,8) belongs to the second region (offsets 0 and 4)
    bbox = det._bbox_for_span(4, 8, regions, [0, 4])
    assert bbox is not None and bbox.y == 20


def test_unlocatable_span_returns_none():
    regions = [{"text": "hello world",
                "bbox": {"x": 0, "y": 0, "width": 110, "height": 20}}]
    det = _detector()
    assert det._bbox_for_span(50, 60, regions, [0]) is None


def test_detect_end_to_end_bbox_and_none():
    det = _detector()
    text = "Mail a@b.co now"  # email regex match at [5, 10)
    regions = [{"text": text,
                "bbox": {"x": 10, "y": 5, "width": 300, "height": 30}}]
    dets = det.detect(text, regions)
    assert len(dets) == 1
    assert dets[0].bounding_box is not None
    # detections without any region get bbox=None, never fabricated
    dets2 = det.detect(text, [])
    assert dets2[0].bounding_box is None
    dets3 = det.detect(text, None)
    assert dets3[0].bounding_box is None


def test_bbox_never_outside_region_bounds():
    det = _detector()
    region = {"text": "x" * 100,
              "bbox": {"x": 7, "y": 3, "width": 500, "height": 25}}
    for span in [(0, 1), (99, 100), (0, 100), (33, 66)]:
        bbox = det._bbox_for_span(*span, [region], [0])
        assert bbox.x >= 7
        assert bbox.x + bbox.width <= 7 + 500
        assert bbox.width >= 1
