"""Layer 2 (spaCy) and Layer 3 (LLM) unit tests — heavy deps mocked."""

import json
import sys
import types

from app.services.pii_detector import PIIDetector


def test_spacy_layer_maps_labels(monkeypatch):
    ent = types.SimpleNamespace(label_="PERSON", start_char=7, end_char=18)

    class _FakeNLP:
        def __call__(self, text):
            return types.SimpleNamespace(ents=[ent])

    det = PIIDetector(enable_spacy=True, enable_llm=False)
    monkeypatch.setattr(det, "_nlp", _FakeNLP())
    monkeypatch.setattr(det, "_spacy_checked", True)
    spans = det._spacy_spans("Hello, Rahul Sharma!")
    assert spans == [("name", 7, 18, 0.80, "spacy")]


def test_spacy_missing_model_graceful_skip(monkeypatch, caplog):
    # Simulate spaCy not installed at all.
    monkeypatch.setitem(sys.modules, "spacy", None)
    det = PIIDetector(enable_spacy=True, enable_llm=False)
    assert det._get_nlp() is None
    assert det.detect("Rahul Sharma lives in Pune.") is not None  # no crash


def test_spacy_disabled_flag():
    det = PIIDetector(enable_spacy=False, enable_llm=False)
    assert det._get_nlp() is None


def _fake_requests(monkeypatch, payload):
    class _Resp:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"response": payload}

    fake = types.ModuleType("requests")
    fake.post = lambda *a, **k: _Resp()
    monkeypatch.setitem(sys.modules, "requests", fake)


def test_llm_layer_parses_and_clamps_confidence(monkeypatch):
    payload = json.dumps([
        {"type": "name", "text": "Rahul Sharma", "confidence": 0.99},
        {"type": "address", "text": "Pune", "confidence": 0.1},
        {"type": "bogus", "text": "ignored", "confidence": 0.9},
    ])
    _fake_requests(monkeypatch, payload)
    det = PIIDetector(enable_spacy=False, enable_llm=True)
    spans = det._llm_spans("Rahul Sharma lives in Pune.")
    by_type = {t: c for t, _s, _e, c, src in spans}
    assert by_type["name"] == 0.95      # clamped to [0.5, 0.95]
    assert by_type["address"] == 0.5
    assert "bogus" not in by_type
    assert all(src == "llm" for *_x, src in spans)


def test_llm_failure_never_crashes(monkeypatch):
    fake = types.ModuleType("requests")

    def _boom(*a, **k):
        raise ConnectionError("ollama down")

    fake.post = _boom
    monkeypatch.setitem(sys.modules, "requests", fake)
    det = PIIDetector(enable_spacy=False, enable_llm=True)
    assert det._llm_spans("anything") == []


def test_llm_unparseable_output_skipped(monkeypatch):
    _fake_requests(monkeypatch, "I cannot help with that.")
    det = PIIDetector(enable_spacy=False, enable_llm=True)
    assert det._llm_spans("text") == []


def test_llm_disabled_by_default(monkeypatch):
    det = PIIDetector(enable_spacy=False, enable_llm=False)
    monkeypatch.setattr("app.services.pii_detector.settings.ENABLE_LLM", False)
    assert det._llm_spans("Rahul Sharma") == []
