"""Three-layer PII detection pipeline (SPEC 1.1).

Layer 1: regex with checksum/range validators (Verhoeff for Aadhaar,
         Luhn for credit cards, octet ranges for IPs, real dates for DOB).
Layer 2: spaCy NER (en_core_web_sm), lazy-loaded, controlled by
         ENABLE_SPACY. If spaCy or the model is missing, a warning is
         logged and the layer is skipped.
Layer 3: Ollama LLM zero-shot JSON prompt, only when ENABLE_LLM=true.
         NOTE: LLM confidence is model-reported, not calibrated; it is
         clamped to [0.5, 0.95] and labeled source="llm". Any LLM failure
         is logged and skipped — it never crashes the pipeline.

Bounding boxes: pixel boxes are computed by proportional interpolation of
the character span inside the owning OCR region's bbox — character
indices are never mixed with pixel coordinates. Spans that cannot be
located in any region are returned with bbox=None and are excluded from
masking; a box is never fabricated.
"""

import json
import logging
import re
import uuid
from datetime import date
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings
from app.models.schemas import BoundingBox, PIIDetection

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Checksum / range validators
# ---------------------------------------------------------------------------

_VERHOEFF_D = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 2, 3, 4, 0, 6, 7, 8, 9, 5],
    [2, 3, 4, 0, 1, 7, 8, 9, 5, 6],
    [3, 4, 0, 1, 2, 8, 9, 5, 6, 7],
    [4, 0, 1, 2, 3, 9, 5, 6, 7, 8],
    [5, 9, 8, 7, 6, 0, 4, 3, 2, 1],
    [6, 5, 9, 8, 7, 1, 0, 4, 3, 2],
    [7, 6, 5, 9, 8, 2, 1, 0, 4, 3],
    [8, 7, 6, 5, 9, 3, 2, 1, 0, 4],
    [9, 8, 7, 6, 5, 4, 3, 2, 1, 0],
]
_VERHOEFF_P = [
    [0, 1, 2, 3, 4, 5, 6, 7, 8, 9],
    [1, 5, 7, 6, 2, 8, 3, 0, 9, 4],
    [5, 8, 0, 3, 7, 9, 6, 1, 4, 2],
    [8, 9, 1, 6, 0, 4, 3, 5, 2, 7],
    [9, 4, 5, 3, 1, 2, 6, 8, 7, 0],
    [4, 2, 8, 6, 5, 7, 3, 9, 0, 1],
    [2, 7, 9, 3, 8, 0, 6, 4, 1, 5],
    [7, 0, 4, 6, 9, 1, 3, 2, 5, 8],
]


def verhoeff_validate(number: str) -> bool:
    """Validate a digit string against the Verhoeff checksum (Aadhaar)."""
    digits = [int(c) for c in number if c.isdigit()]
    if not digits:
        return False
    c = 0
    for i, d in enumerate(reversed(digits)):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][d]]
    return c == 0


def verhoeff_check_digit(first_digits: str) -> int:
    """Compute the Verhoeff check digit for the given leading digits."""
    digits = [int(c) for c in first_digits]
    c = 0
    for i, d in enumerate(reversed(digits), start=1):
        c = _VERHOEFF_D[c][_VERHOEFF_P[i % 8][d]]
    for v in range(10):
        if _VERHOEFF_D[c][v] == 0:
            return v
    return 0  # unreachable


def luhn_validate(number: str) -> bool:
    """Validate a digit string against the Luhn checksum (credit cards)."""
    digits = [int(c) for c in number if c.isdigit()]
    if not digits:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def luhn_check_digit(first_digits: str) -> int:
    """Compute the Luhn check digit for the given leading digits."""
    for v in range(10):
        if luhn_validate(first_digits + str(v)):
            return v
    return 0  # unreachable


def valid_ip(ip: str) -> bool:
    try:
        return all(0 <= int(octet) <= 255 for octet in ip.split("."))
    except ValueError:
        return False


def valid_date_string(text: str) -> bool:
    """Accept dd/mm/yyyy, dd-mm-yyyy, dd.mm.yyyy (and yyyy-first) within
    a sane year range with real calendar validation."""
    m = re.match(r"^(\d{1,4})[-/.](\d{1,2})[-/.](\d{1,4})$", text.strip())
    if not m:
        return False
    a, b, c = (int(g) for g in m.groups())
    if a > 31:  # yyyy-mm-dd
        year, month, day = a, b, c
    else:  # dd-mm-yyyy (or 2-digit year)
        day, month, year = a, b, c
        if year < 100:
            year += 1900 if year > 30 else 2000
    if not (1900 <= year <= 2100):
        return False
    try:
        date(year, month, day)
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------------------
# Regex layer
# ---------------------------------------------------------------------------

class _Pattern:
    def __init__(self, pii_type: str, pattern: str, confidence: float, validator=None):
        self.pii_type = pii_type
        self.pattern = re.compile(pattern)
        self.confidence = confidence
        self.validator = validator


def _digits_only(s: str) -> str:
    return re.sub(r"\D", "", s)


def _compile_patterns() -> List[_Pattern]:
    return [
        _Pattern("email", r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", 0.95),
        _Pattern(
            "phone",
            r"(?<!\d)(?:\+91[-\s]?)?[6-9]\d{4}[-\s]?\d{5}(?!\d)"
            r"|(?<!\d)\+\d{1,3}[-\s]\d{3}[-\s]\d{3}[-\s]\d{4}(?!\d)",
            0.90,
        ),
        _Pattern(
            "aadhaar",
            r"(?<!\d)(?<!\d{4}[-\s])\d{4}[-\s]?\d{4}[-\s]?\d{4}(?!\d)(?![-\s]?\d)",
            0.95,
            validator=lambda m: verhoeff_validate(_digits_only(m)),
        ),
        _Pattern("pan", r"\b[A-Z]{5}\d{4}[A-Z]\b", 0.95),
        _Pattern(
            "credit_card",
            r"(?<!\d)(?:\d{4}[-\s]?){3}\d{4}(?!\d)",
            0.90,
            validator=lambda m: luhn_validate(_digits_only(m)),
        ),
        _Pattern(
            "ip",
            r"\b(?:\d{1,3}\.){3}\d{1,3}\b",
            0.85,
            validator=valid_ip,
        ),
        _Pattern(
            "dob",
            r"\b\d{1,2}[-/.]\d{1,2}[-/.]\d{2,4}\b|\b\d{4}[-/.]\d{1,2}[-/.]\d{1,2}\b",
            0.75,
            validator=valid_date_string,
        ),
        _Pattern("ssn", r"\b\d{3}-\d{2}-\d{4}\b", 0.85),
        _Pattern("url", r"\bhttps?://[^\s\"'<>]+|\bwww\.[^\s\"'<>]+", 0.90),
    ]


_SPACY_LABEL_MAP = {
    "PERSON": "name",
    "GPE": "address",
    "LOC": "address",
    "FAC": "address",
    "ORG": "organization",
    "DATE": "dob",
}

_LLM_PROMPT = """Analyze the following text and identify all Personally Identifiable Information (PII).
For each item return: type, text, confidence (0.0-1.0).

Text: \"\"\"{text}\"\"\"

Respond ONLY with a JSON array like:
[{{"type": "name", "text": "Rahul Sharma", "confidence": 0.9}}]

Allowed types: name, email, phone, address, aadhaar, pan, dob, credit_card, ip, ssn, url, organization"""

_LLM_TYPES = {
    "name", "email", "phone", "address", "aadhaar", "pan", "dob",
    "credit_card", "ip", "ssn", "url", "organization",
}


class PIIDetector:
    """Multi-layer PII detector. Every layer is optional and degrades
    gracefully: a missing spaCy model or an unreachable LLM only disables
    that layer."""

    def __init__(self, enable_spacy: Optional[bool] = None, enable_llm: Optional[bool] = None):
        self.patterns = _compile_patterns()
        self.enable_spacy = settings.ENABLE_SPACY if enable_spacy is None else enable_spacy
        self.enable_llm = settings.ENABLE_LLM if enable_llm is None else enable_llm
        self._nlp = None
        self._spacy_checked = False

    # -- layer 2 lazy loader ------------------------------------------------
    def _get_nlp(self):
        if self._spacy_checked:
            return self._nlp
        self._spacy_checked = True
        if not self.enable_spacy:
            return None
        try:
            import spacy  # lazy import — spaCy is an optional dependency

            self._nlp = spacy.load(settings.SPACY_MODEL)
            logger.info("spaCy model %s loaded", settings.SPACY_MODEL)
        except Exception:
            logger.warning(
                "spaCy model %s unavailable — NER layer skipped", settings.SPACY_MODEL
            )
            self._nlp = None
        return self._nlp

    # -- span producers ------------------------------------------------------
    def _regex_spans(self, text: str) -> List[Tuple[str, int, int, float, str]]:
        spans = []
        for p in self.patterns:
            for m in p.pattern.finditer(text):
                if p.validator is not None and not p.validator(m.group()):
                    continue
                spans.append((p.pii_type, m.start(), m.end(), p.confidence, "regex"))
        return spans

    def _spacy_spans(self, text: str) -> List[Tuple[str, int, int, float, str]]:
        nlp = self._get_nlp()
        if nlp is None or not text.strip():
            return []
        try:
            doc = nlp(text)
        except Exception:
            logger.warning("spaCy NER failed — layer skipped for this input")
            return []
        spans = []
        for ent in doc.ents:
            pii_type = _SPACY_LABEL_MAP.get(ent.label_)
            if pii_type:
                spans.append((pii_type, ent.start_char, ent.end_char, 0.80, "spacy"))
        return spans

    def _llm_spans(self, text: str) -> List[Tuple[str, int, int, float, str]]:
        """Layer 3: Ollama zero-shot extraction.

        Confidence values are model-reported (NOT calibrated) and are
        clamped to [0.5, 0.95]. Any failure is logged and skipped.
        """
        if not self.enable_llm or not text.strip():
            return []
        try:
            import requests

            resp = requests.post(
                f"{settings.OLLAMA_HOST}/api/generate",
                json={
                    "model": settings.LLM_MODEL,
                    "prompt": _LLM_PROMPT.format(text=text),
                    "stream": False,
                },
                timeout=settings.LLM_TIMEOUT,
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "")
        except Exception as exc:
            logger.warning("LLM layer unavailable (%s) — skipped", type(exc).__name__)
            return []
        try:
            match = re.search(r"\[.*\]", raw, re.DOTALL)
            items = json.loads(match.group()) if match else []
        except (ValueError, AttributeError):
            logger.warning("LLM returned unparseable output — skipped")
            return []
        spans = []
        for item in items:
            try:
                pii_type = str(item.get("type", "")).lower()
                value = str(item.get("text", ""))
                if pii_type not in _LLM_TYPES or not value:
                    continue
                start = text.find(value)
                if start < 0:
                    continue
                conf = min(0.95, max(0.5, float(item.get("confidence", 0.7))))
                spans.append((pii_type, start, start + len(value), conf, "llm"))
            except (TypeError, ValueError):
                continue
        return spans

    def detect_spans(self, full_text: str) -> List[Tuple[str, int, int, float, str]]:
        """All layers merged at span level: (pii_type, start, end, confidence, source)."""
        spans = self._regex_spans(full_text)
        spans += self._spacy_spans(full_text)
        spans += self._llm_spans(full_text)
        return spans

    # -- bbox math (CRITICAL FIX, SPEC 1.1) ----------------------------------
    @staticmethod
    def _region_offsets(full_text: str, regions: List[Dict[str, Any]]) -> List[int]:
        """Locate each region's text inside full_text (sequential search)."""
        offsets: List[int] = []
        pos = 0
        for region in regions:
            rtext = region.get("text", "")
            idx = full_text.find(rtext, pos) if rtext else -1
            if idx == -1 and rtext:
                idx = full_text.find(rtext)
            offsets.append(idx)
            if idx >= 0:
                pos = idx + len(rtext)
        return offsets

    @staticmethod
    def _bbox_for_span(
        start: int,
        end: int,
        regions: List[Dict[str, Any]],
        offsets: List[int],
    ) -> Optional[BoundingBox]:
        """Proportional interpolation of the char span inside the owning
        region's pixel bbox. Returns None when the span cannot be located —
        a box is never fabricated."""
        for region, rstart in zip(regions, offsets):
            if rstart < 0:
                continue
            rtext = region.get("text", "")
            if not rtext:
                continue
            rend = rstart + len(rtext)
            if rstart <= start and end <= rend:
                local_start = start - rstart
                local_end = end - rstart
                length = len(rtext)
                bbox = region["bbox"]
                x = bbox["x"] + int((local_start / length) * bbox["width"])
                width = int(((local_end - local_start) / length) * bbox["width"])
                return BoundingBox(
                    x=int(x),
                    y=int(bbox["y"]),
                    width=max(1, int(width)),
                    height=int(bbox["height"]),
                )
        return None

    # -- public API -----------------------------------------------------------
    def detect(
        self, full_text: str, regions: Optional[List[Dict[str, Any]]] = None
    ) -> List[PIIDetection]:
        """Run all enabled layers and return merged PIIDetection objects.

        `regions` are OCR regions: {"text": str, "bbox": {"x","y","width","height"}}.
        When regions is None (pure text evaluation) all detections get bbox=None.
        """
        regions = regions or []
        offsets = self._region_offsets(full_text, regions)
        detections: List[PIIDetection] = []
        for pii_type, start, end, confidence, source in self.detect_spans(full_text):
            text = full_text[start:end]
            bbox = self._bbox_for_span(start, end, regions, offsets) if regions else None
            detections.append(
                PIIDetection(
                    id=uuid.uuid4().hex,
                    pii_type=pii_type,
                    text=text,
                    bounding_box=bbox,
                    confidence=round(float(confidence), 3),
                    source=source,
                )
            )
        return merge_detections(detections)


def _bbox_key(bbox: Optional[BoundingBox]) -> Optional[Tuple[int, int, int, int]]:
    if bbox is None:
        return None
    return (round(bbox.x), round(bbox.y), round(bbox.width), round(bbox.height))


def merge_detections(detections: List[PIIDetection]) -> List[PIIDetection]:
    """Dedup on (pii_type, text.lower(), rounded bbox).

    The same text at two different locations yields separate detections;
    duplicates of the same span keep the highest confidence.
    """
    best: Dict[Tuple[str, str, Optional[Tuple[int, int, int, int]]], PIIDetection] = {}
    order: List[Tuple[str, str, Optional[Tuple[int, int, int, int]]]] = []
    for det in detections:
        key = (det.pii_type, det.text.lower(), _bbox_key(det.bounding_box))
        if key not in best:
            best[key] = det
            order.append(key)
        elif det.confidence > best[key].confidence:
            best[key] = det
    return [best[k] for k in order]
