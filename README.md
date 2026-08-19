# RedactFlow v2 — Local PII Detection & Redaction Engine

> Detect, review, and redact personally identifiable information (PII) in images and PDFs — locally, with a three-layer detection pipeline, a human-in-the-loop review UI, and a reproducible evaluation framework.

RedactFlow v2 is a BTech final-year project: a FastAPI + React/TypeScript application that finds PII in scanned/photographed documents and redacts it with six different masking styles. Everything runs on your own machine — no cloud APIs are involved.

---

## Features

Every feature below is implemented in this repository (see `backend/` and `frontend/`). Nothing listed here is aspirational.

* **Three-layer PII detection** (each layer optional, graceful degradation):

  1. **Regex layer** — EMAIL, PHONE (Indian `+91` and generic), AADHAAR with **Verhoeff checksum validation**, PAN, CREDIT_CARD with **Luhn check**, IP (octets validated 0–255), DOB (valid date ranges), SSN, URL.
  2. **spaCy NER layer** — `en_core_web_sm`, mapping PERSON→NAME, GPE/LOC/FAC→ADDRESS, ORG→ORGANIZATION, DATE→DOB. Lazy-loaded; skipped with a warning if the model is missing (`ENABLE_SPACY=false` to disable).
  3. **Optional local LLM layer** — zero-shot JSON extraction via Ollama, only when `ENABLE_LLM=true`. Timeouts and failures degrade gracefully (log + skip, never crash). LLM confidence is clamped to `[0.5, 0.95]` and is *model-reported, not calibrated*.

* **Six masking styles**: blur, pixelate, blackbox, redbox (proper semi-transparent RGBA composite), whitebox, and **synthetic replacement** — format-preserving fake data generated with Faker (`en_IN`), scaled to fit the original bounding box (email stays email-shaped, phone keeps digit count, etc.).

* **Human-in-the-loop review**: after detection, uncheck any detection in the UI and the document is **re-masked from the stored original without re-running OCR/LLM** (`/jobs/{id}/remask`), with a confidence-threshold slider.

* **PDF support**: page-by-page processing at 150 DPI, up to **25 pages** (413 if exceeded), with per-page before/after preview and real measured `processing_time_ms`.

* **Real async batch processing**: up to **20 files** per batch, processed by a background worker with a real `queued → processing → completed` lifecycle, progress polling, and a **ZIP download** of all masked outputs.

* **History & audit**: last 50 jobs persisted in SQLite (`/history`), with re-download of masked outputs and deletion. Stored artifacts have a **7-day TTL** cleanup.

* **Evaluation framework** (the academic core): a 60-document synthetic dataset with ground-truth spans, span-level Precision/Recall/F1 per entity type, an ablation over the three detector configurations, latency benchmarks, and a **leak-test** that re-OCRs masked output to verify no PII string survives.

* **Security controls**: optional `X-API-Key` auth, 30 req/min rate limiting on POST endpoints, magic-byte file validation, 10 MB size cap, filename sanitization, explicit CORS, and sanitized error responses.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Client: Browser (React 18 + TypeScript + Vite)                   │
│  ├── Home / Batch / PDF / History pages                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ multipart / JSON
┌─────────────────────────────────────────────────────────────────┐
│  Server: FastAPI backend (uvicorn :8000)                        │
│  ├── Routers (/api/v1)                                          │
│  │   ├── health · process · jobs · batch · pdf · history        │
│  ├── PIIDetector                                                │
│  │   ├── Layer 1: Regex                                         │
│  │   ├── Layer 2: spaCy NER                                     │
│  │   └── Layer 3: LLM (optional)                                │
│  ├── EasyOCR service                                            │
│  ├── Masking + Synthetic services (Faker en_IN)                 │
│  ├── Leak-test verification                                     │
│  ├── Evaluation framework (dataset · evaluate · benchmark)      │
│  └── SQLite (jobs · detections · batches)                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ ENABLE_LLM=true only
┌─────────────────────────────────────────────────────────────────┐
│  External: Local runtime (optional)                             │
│  └── Ollama (llama3.2:3b)                                       │
└─────────────────────────────────────────────────────────────────┘
```

The production container is a single image: `node:20-alpine` builds the SPA, and `python:3.11-slim` runs uvicorn, serving the SPA via `StaticFiles` at `/` and the API under `/api/v1`.

---

## Quick Start

### Option 1 — Docker (recommended)

```bash
git clone https://github.com/monikasharma0099/Redactflow__s
cd redactflow-v2
docker compose up --build
# open http://localhost:8000
```

The stack starts two services: `redactflow` (app) and `ollama` (pinned `ollama/ollama:0.3.12`). Detection works out of the box in **regex + spaCy** mode — fully local.

**To enable the optional LLM layer:**

```bash
# one-time model pull into the Ollama container
docker exec redactflow-ollama ollama pull llama3.2:3b
# then set ENABLE_LLM=true in docker-compose.yml and restart
docker compose up -d
```

> **Privacy note:** with `ENABLE_LLM=true`, extracted document text is sent to `OLLAMA_HOST`. Keep it pointing at a *local* Ollama instance. See [docs/PRIVACY.md](docs/PRIVACY.md).

### Option 2 — Manual (development)

**Backend:**

```bash
cd backend
python -m venv venv && source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
pip install https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl
uvicorn main:app --reload    # http://localhost:8000
```

**Frontend:**

```bash
cd frontend
npm ci
npm run dev                  # http://localhost:5173 (proxy to backend)
```

**Run the test suite** (no network, GPU, or Ollama required — heavy deps are mocked):

```bash
cd backend
python -m pytest tests/ -q --cov=app --cov-report=term-missing
```

**Run the evaluation framework:**

```bash
cd backend
python -m app.evaluation.dataset_generator   # writes backend/evaluation/dataset.json
python -m app.evaluation.evaluate            # writes results/metrics.md + metrics.json
python -m app.evaluation.benchmark           # writes results/benchmarks.md
python -m app.services.leak_test             # leak-test verification demo
```

---

## API

All endpoints are prefixed with `/api/v1`. Errors return `{"detail": "human readable"}`.

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | `{status, ollama, spacy, version}` |
| POST | `/process` | Upload one image (PNG/JPEG, ≤10 MB) + `mask_type` + `confidence_threshold` → detections + masked/original PNGs (base64) |
| POST | `/jobs/{job_id}/remask` | Re-mask stored job with new style/exclusions/threshold — no re-OCR. 404 for unknown job |
| GET | `/jobs/{job_id}/download` | Stream the masked PNG of a stored job |
| POST | `/batch` | Upload ≤20 files → returns `batch_id` immediately; background worker processes |
| GET | `/batch/{batch_id}` | Batch lifecycle: `queued → processing → completed`, per-file status |
| GET | `/batch/{batch_id}/download` | ZIP of masked PNGs (404 until completed) |
| POST | `/pdf` | Upload PDF (≤25 pages, else 413) → per-page detections + images |
| GET | `/history` | Last 50 jobs |
| DELETE | `/history/{job_id}` | Delete a job and its artifacts |

---

## Configuration

All settings are environment variables (see `backend/.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `ENABLE_LLM` | `false` | Enable Layer-3 LLM detection via Ollama |
| `ENABLE_SPACY` | `true` | Enable Layer-2 spaCy NER |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama base URL (**extracted text is sent here when LLM is on**) |
| `LLM_MODEL` | `llama3.2:3b` | Ollama model name |
| `LLM_TIMEOUT` | `30` | LLM request timeout (seconds) |
| `MAX_FILE_SIZE` | `10485760` | Max upload size in bytes (10 MB) |
| `MAX_PDF_PAGES` | `25` | PDF page cap (413 beyond) |
| `BATCH_MAX_FILES` | `20` | Max files per batch |
| `DATA_DIR` | `./data` | SQLite DB + stored artifacts location |
| `API_KEY` | *(unset)* | If set, all `/api/v1` endpoints except `/health` require header `X-API-Key`. **If unset, the API is open** — acceptable for local use only |
| `CORS_ORIGINS` | localhost dev origins | Explicit allow-list; credentials disabled |

---

## Evaluation Results

The evaluation runs the detector (text-level, no OCR) over **60 synthetic documents** (invoices, resumes, medical notes, bank statements, ID forms, complaint letters) with known ground-truth spans, in three configurations — regex-only, regex+spaCy, regex+spaCy+LLM — computing span-level exact-match Precision/Recall/F1 per entity type. Full methodology: [docs/REPORT.md](docs/REPORT.md#7-testing--evaluation); raw output: `backend/evaluation/results/`.

**Measured configuration: `regex-only`.** The `regex+spaCy` and `regex+spaCy+LLM` configurations were **not run** in the measurement environment (the spaCy `en_core_web_sm` model was not importable there, and Ollama was unavailable / `ENABLE_LLM=false`), so only the regex layer is reported below. Raw data: `backend/evaluation/results/metrics.md`.

| Entity type | Precision | Recall | F1 | TP | FP | FN |
|-------------|-----------|--------|----|----|----|----|
| aadhaar | 1.000 | 1.000 | 1.000 | 20 | 0 | 0 |
| credit_card | 1.000 | 1.000 | 1.000 | 20 | 0 | 0 |
| dob | 1.000 | 1.000 | 1.000 | 30 | 0 | 0 |
| email | 1.000 | 1.000 | 1.000 | 50 | 0 | 0 |
| ip | 1.000 | 1.000 | 1.000 | 10 | 0 | 0 |
| pan | 1.000 | 1.000 | 1.000 | 30 | 0 | 0 |
| phone | 1.000 | 1.000 | 1.000 | 60 | 0 | 0 |
| name | 0.000 | 0.000 | 0.000 | 0 | 0 | 60 |
| address | 0.000 | 0.000 | 0.000 | 0 | 0 | 40 |
| organization | 0.000 | 0.000 | 0.000 | 0 | 0 | 40 |
| **OVERALL** | **1.000** | **0.611** | **0.759** | **220** | **0** | **140** |

**Reading the numbers:** the regex layer achieves **perfect precision** — checksum validation (Verhoeff for Aadhaar, Luhn for cards), IP-octet and date-range gating eliminate every false positive in the dataset. The recall gap (0.611) is *exactly* the context-dependent entities (name/address/organization) that regular expressions cannot express by design; detecting those is the job of the spaCy NER layer and the optional LLM layer. That is the intended ablation story: Layer 1 is a high-precision floor, Layers 2–3 exist to add recall on context entities.

Latency benchmarks, measured **CPU-only** (no GPU; values are hardware-dependent). Raw data: `backend/evaluation/results/benchmarks.md`.

| Benchmark | Mean | p95 | Notes |
|-----------|------|-----|-------|
| Regex detection, per document (60 docs) | 0.101 ms | 0.14 ms | max 0.227 ms |
| Synthetic replacement generation (1000 gens) | 0.02 ms | 0.0499 ms | stateless Faker `en_IN` |
| Masking — blur (800×600 image, 3 detections) | 1.123 ms | 2.098 ms | |
| Masking — pixelate | 0.277 ms | 0.324 ms | |
| Masking — blackbox | 0.265 ms | 0.653 ms | |
| Masking — redbox | 9.866 ms | 11.322 ms | RGBA alpha composite |
| Masking — whitebox | 0.219 ms | 0.297 ms | |
| Masking — synthetic | 10.785 ms | 12.121 ms | includes font-fit text rendering |

---

## Security & Privacy

* **Local-first**: regex + spaCy mode never sends document content anywhere. The optional LLM layer sends extracted text only to `OLLAMA_HOST` (default: a local container).
* **Retention**: stored jobs and artifacts are deleted after **7 days** (startup cleanup).
* **Auth/rate-limiting**: optional API key; 30 req/min per IP on POSTs.
* Full threat model, data-flow diagram, and DPIA-style analysis: [**docs/PRIVACY.md**](docs/PRIVACY.md). Design decisions: [**docs/ARCHITECTURE.md**](docs/ARCHITECTURE.md).

---

## Limitations

Honest bounds, by design:

* **OCR accuracy bounds detection.** Detection happens on OCR-extracted text; characters the OCR misreads cannot be matched, and bounding boxes are computed by proportional interpolation inside OCR text regions — skewed or low-resolution scans degrade both.
* **LLM confidence is model-reported, not calibrated.** A 0.9 from the LLM is the model's own claim, clamped to `[0.5, 0.95]`; treat it as a hint, not a probability.
* **Language/locale focus**: English text with Indian document formats (Aadhaar, PAN, +91 phones). Other locales need new patterns and Faker locales.
* **No handwritten-text guarantee**: EasyOCR supports handwriting only partially; handwritten PII may be missed.
* SQLite + in-process background tasks are a deliberate single-node simplification (see docs/ARCHITECTURE.md for the tradeoff).

---

## Project Structure

```
redactflow-v2/
├── backend/
│   ├── app/
│   │   ├── core/            # config, database, security, rate_limit
│   │   ├── models/          # pydantic schemas, SQLAlchemy models
│   │   ├── services/        # pii_detector, ocr, masking, pdf, synthetic,
│   │   │                    # job_service, leak_test
│   │   ├── routers/         # health, process, batch, pdf, history
│   │   └── evaluation/      # dataset_generator, evaluate, benchmark
│   ├── evaluation/          # generated dataset + results artifacts
│   ├── tests/               # pytest (≥25 tests, heavy deps mocked)
│   ├── main.py
│   └── requirements.txt     # pinned
├── frontend/                # React 18 + TS + Vite + Tailwind + framer-motion
├── docs/
│   ├── REPORT.md            # final-year project report
│   ├── PRIVACY.md           # threat model, retention, DPIA-style analysis
│   └── ARCHITECTURE.md      # diagrams, design decisions & tradeoffs
├── .github/workflows/ci.yml # backend tests + frontend build + docker build
├── Dockerfile               # multi-stage all-in-one image
├── docker-compose.yml       # redactflow + pinned ollama
└── .dockerignore
```

---

## License

[MIT](LICENSE) — free to use, modify, and distribute with attribution.
