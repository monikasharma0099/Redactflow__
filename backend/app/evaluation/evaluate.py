"""Detector evaluation (SPEC 1.6).

Runs the text-level detector (no OCR) over the synthetic dataset in up to
three configurations — regex-only, regex+spacy, regex+spacy+llm (LLM is
skipped unless ENABLE_LLM=true and Ollama is reachable; spaCy is skipped
if the model is not importable) — and computes span-level exact-match
Precision/Recall/F1 on (type, start, end), per entity type and overall.

Writes backend/evaluation/results/metrics.md and metrics.json.

Usage: python -m app.evaluation.evaluate
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Set, Tuple

from app.core.config import settings
from app.services.pii_detector import PIIDetector

logger = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).resolve().parents[2] / "evaluation" / "results"
DATASET_PATH = Path(__file__).resolve().parents[2] / "evaluation" / "dataset.json"

Span = Tuple[str, int, int]


def _spacy_available() -> bool:
    if not settings.ENABLE_SPACY:
        return False
    try:
        import importlib.util

        return (importlib.util.find_spec("spacy") is not None
                and importlib.util.find_spec(settings.SPACY_MODEL) is not None)
    except Exception:
        return False


def _llm_available() -> bool:
    if not settings.ENABLE_LLM:
        return False
    try:
        import requests

        return requests.get(f"{settings.OLLAMA_HOST}/api/tags", timeout=2).status_code == 200
    except Exception:
        return False


def _predict_spans(detector: PIIDetector, text: str) -> Set[Span]:
    return {(t, s, e) for t, s, e, _conf, _src in detector.detect_spans(text)}


def _score(gold: Set[Span], pred: Set[Span]) -> Dict[str, float]:
    tp = len(gold & pred)
    fp = len(pred - gold)
    fn = len(gold - pred)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn,
            "precision": round(precision, 4), "recall": round(recall, 4),
            "f1": round(f1, 4)}


def evaluate_config(detector: PIIDetector, docs: List[Dict]) -> Dict:
    per_type: Dict[str, Dict[str, int]] = {}
    overall = {"tp": 0, "fp": 0, "fn": 0}
    for doc in docs:
        pred = _predict_spans(detector, doc["text"])
        gold = {(e["type"], e["start"], e["end"]) for e in doc["entities"]}
        types = {t for t, _, _ in gold} | {t for t, _, _ in pred}
        for t in types:
            g = {s for s in gold if s[0] == t}
            p = {s for s in pred if s[0] == t}
            tp, fp, fn = len(g & p), len(p - g), len(g - p)
            bucket = per_type.setdefault(t, {"tp": 0, "fp": 0, "fn": 0})
            bucket["tp"] += tp
            bucket["fp"] += fp
            bucket["fn"] += fn
            overall["tp"] += tp
            overall["fp"] += fp
            overall["fn"] += fn

    def prf(c):
        p = c["tp"] / (c["tp"] + c["fp"]) if c["tp"] + c["fp"] else 0.0
        r = c["tp"] / (c["tp"] + c["fn"]) if c["tp"] + c["fn"] else 0.0
        f = 2 * p * r / (p + r) if p + r else 0.0
        return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4), **c}

    return {
        "overall": prf(overall),
        "per_type": {t: prf(c) for t, c in sorted(per_type.items())},
    }


def _md_table(metrics: Dict) -> str:
    lines = ["| Entity type | Precision | Recall | F1 | TP | FP | FN |",
             "|---|---|---|---|---|---|---|"]
    for t, m in metrics["per_type"].items():
        lines.append(f"| {t} | {m['precision']:.3f} | {m['recall']:.3f} | "
                     f"{m['f1']:.3f} | {m['tp']} | {m['fp']} | {m['fn']} |")
    o = metrics["overall"]
    lines.append(f"| **OVERALL** | **{o['precision']:.3f}** | **{o['recall']:.3f}** | "
                 f"**{o['f1']:.3f}** | {o['tp']} | {o['fp']} | {o['fn']} |")
    return "\n".join(lines)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    docs = json.loads(DATASET_PATH.read_text())

    spacy_ok = _spacy_available()
    llm_ok = _llm_available()

    configs = [("regex-only", PIIDetector(enable_spacy=False, enable_llm=False))]
    if spacy_ok:
        configs.append(("regex+spacy", PIIDetector(enable_spacy=True, enable_llm=False)))
    if llm_ok:
        configs.append(("regex+spacy+llm", PIIDetector(enable_spacy=spacy_ok, enable_llm=True)))

    notes = []
    if not spacy_ok:
        notes.append("- `regex+spacy` **skipped**: spaCy / en_core_web_sm not importable "
                     "in this environment.")
    if not llm_ok:
        notes.append("- `regex+spacy+llm` **skipped**: ENABLE_LLM=false or Ollama "
                     "unreachable.")

    results = {}
    for name, detector in configs:
        logger.info("Evaluating configuration: %s", name)
        results[name] = evaluate_config(detector, docs)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "metrics.json").write_text(json.dumps(
        {"dataset": str(DATASET_PATH.name), "n_documents": len(docs),
         "configs_run": [n for n, _ in configs],
         "configs_skipped": notes, "results": results}, indent=2))

    lines = ["# RedactFlow v2 — Detection Evaluation",
             "",
             f"Dataset: `{DATASET_PATH.name}` ({len(docs)} synthetic documents, "
             f"{sum(len(d['entities']) for d in docs)} ground-truth PII spans).",
             "",
             "Metric: span-level exact match on `(type, start, end)` — micro-averaged "
             "Precision / Recall / F1.",
             "",
             f"Configurations run: {', '.join(n for n, _ in configs)}.",
             ""]
    if notes:
        lines += ["**Skipped configurations:**", ""] + notes + [""]
    for name, _ in configs:
        m = results[name]
        o = m["overall"]
        lines += [f"## Configuration: `{name}`",
                  "",
                  f"Overall: **P={o['precision']:.3f} R={o['recall']:.3f} "
                  f"F1={o['f1']:.3f}**",
                  "",
                  _md_table(m), ""]
    (RESULTS_DIR / "metrics.md").write_text("\n".join(lines))

    for name, _ in configs:
        o = results[name]["overall"]
        print(f"{name}: P={o['precision']:.3f} R={o['recall']:.3f} F1={o['f1']:.3f}")
    print(f"Wrote {RESULTS_DIR / 'metrics.md'} and metrics.json")


if __name__ == "__main__":
    main()
