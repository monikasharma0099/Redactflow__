"""Latency benchmarks (SPEC 1.6).

Measures: regex-layer detection latency over the dataset (mean/p95),
synthetic-generation latency, and masking latency on synthetic 800x600
images. Writes backend/evaluation/results/benchmarks.md.

Usage: python -m app.evaluation.benchmark
"""

import json
import statistics
import time
from pathlib import Path

from PIL import Image

from app.models.schemas import BoundingBox, PIIDetection
from app.services.masking_service import MaskingService
from app.services.pii_detector import PIIDetector
from app.services.synthetic_service import SyntheticDataService

RESULTS_DIR = Path(__file__).resolve().parents[2] / "evaluation" / "results"
DATASET_PATH = Path(__file__).resolve().parents[2] / "evaluation" / "dataset.json"


def _p95(values):
    values = sorted(values)
    idx = min(len(values) - 1, int(0.95 * len(values)))
    return values[idx]


def bench_regex(docs) -> dict:
    detector = PIIDetector(enable_spacy=False, enable_llm=False)
    times = []
    for doc in docs:  # warmup-free: every doc timed
        start = time.perf_counter()
        detector.detect_spans(doc["text"])
        times.append((time.perf_counter() - start) * 1000.0)
    return {"n": len(times), "mean_ms": round(statistics.fmean(times), 3),
            "p95_ms": round(_p95(times), 3), "max_ms": round(max(times), 3)}


def bench_synthetic(n: int = 1000) -> dict:
    svc = SyntheticDataService()
    cases = [("email", "a@b.com"), ("phone", "+91 9876543210"),
             ("aadhaar", "1234 5678 9012"), ("pan", "ABCDE1234F"),
             ("credit_card", "4111-1111-1111-1111"), ("name", "Rahul Sharma")]
    times = []
    for i in range(n):
        pii_type, original = cases[i % len(cases)]
        start = time.perf_counter()
        svc.generate(pii_type, original)
        times.append((time.perf_counter() - start) * 1000.0)
    return {"n": n, "mean_ms": round(statistics.fmean(times), 4),
            "p95_ms": round(_p95(times), 4)}


def bench_masking() -> dict:
    svc = MaskingService()
    detections = [
        PIIDetection(id=f"d{i}", pii_type="email", text="user@example.com",
                     bounding_box=BoundingBox(x=50 + i * 200, y=100 + i * 150,
                                              width=180, height=30),
                     confidence=0.95, source="regex")
        for i in range(3)
    ]
    out = {}
    for style in ("blur", "pixelate", "blackbox", "redbox", "whitebox", "synthetic"):
        times = []
        for _ in range(10):
            img = Image.new("RGB", (800, 600), (240, 240, 240))
            start = time.perf_counter()
            svc.apply_mask(img, [d.model_copy() for d in detections], style)
            times.append((time.perf_counter() - start) * 1000.0)
        out[style] = {"mean_ms": round(statistics.fmean(times), 3),
                      "p95_ms": round(_p95(times), 3)}
    return out


def main() -> None:
    docs = json.loads(DATASET_PATH.read_text())
    regex = bench_regex(docs)
    synthetic = bench_synthetic()
    masking = bench_masking()

    lines = ["# RedactFlow v2 — Latency Benchmarks",
             "",
             "Hardware-dependent; values measured on the generation machine "
             "(CPU-only, no GPU).",
             "",
             "## Regex detection layer (per document)",
             "",
             f"- Documents: {regex['n']}",
             f"- Mean: **{regex['mean_ms']} ms**",
             f"- p95: **{regex['p95_ms']} ms**",
             f"- Max: {regex['max_ms']} ms",
             "",
             "## Synthetic replacement generation",
             "",
             f"- Generations: {synthetic['n']}",
             f"- Mean: **{synthetic['mean_ms']} ms**",
             f"- p95: **{synthetic['p95_ms']} ms**",
             "",
             "## Masking latency (800x600 image, 3 detections)",
             "",
             "| Style | Mean (ms) | p95 (ms) |", "|---|---|---|"]
    for style, m in masking.items():
        lines.append(f"| {style} | {m['mean_ms']} | {m['p95_ms']} |")
    lines.append("")

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "benchmarks.md").write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
