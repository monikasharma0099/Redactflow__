# RedactFlow v2 — Detection Evaluation

Dataset: `dataset.json` (60 synthetic documents, 360 ground-truth PII spans).

Metric: span-level exact match on `(type, start, end)` — micro-averaged Precision / Recall / F1.

Configurations run: regex-only.

**Skipped configurations:**

- `regex+spacy` **skipped**: spaCy / en_core_web_sm not importable in this environment.
- `regex+spacy+llm` **skipped**: ENABLE_LLM=false or Ollama unreachable.

## Configuration: `regex-only`

Overall: **P=1.000 R=0.611 F1=0.759**

| Entity type | Precision | Recall | F1 | TP | FP | FN |
|---|---|---|---|---|---|---|
| aadhaar | 1.000 | 1.000 | 1.000 | 20 | 0 | 0 |
| address | 0.000 | 0.000 | 0.000 | 0 | 0 | 40 |
| credit_card | 1.000 | 1.000 | 1.000 | 20 | 0 | 0 |
| dob | 1.000 | 1.000 | 1.000 | 30 | 0 | 0 |
| email | 1.000 | 1.000 | 1.000 | 50 | 0 | 0 |
| ip | 1.000 | 1.000 | 1.000 | 10 | 0 | 0 |
| name | 0.000 | 0.000 | 0.000 | 0 | 0 | 60 |
| organization | 0.000 | 0.000 | 0.000 | 0 | 0 | 40 |
| pan | 1.000 | 1.000 | 1.000 | 30 | 0 | 0 |
| phone | 1.000 | 1.000 | 1.000 | 60 | 0 | 0 |
| **OVERALL** | **1.000** | **0.611** | **0.759** | 220 | 0 | 140 |
