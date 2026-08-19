# ---------------------------------------------------------------------------
# RedactFlow v2 — all-in-one production image (multi-stage)
#
#   Stage 1 (node:20-alpine)   : builds the React/TS frontend -> frontend/dist
#   Stage 2 (python:3.11-slim) : installs backend deps + the spaCy
#                                en_core_web_sm model, copies the built SPA
#                                into /app/static, and runs uvicorn.
#
# Serving contract (SPEC 3): the FastAPI backend mounts /app/static with
# StaticFiles(html=True) at "/" so the container serves the SPA and the API
# under /api/v1 from a single port (8000). The mount itself is implemented
# in backend/main.py; this Dockerfile only guarantees the files exist at
# /app/static.
# ---------------------------------------------------------------------------

# ---------- Stage 1: frontend build ----------------------------------------
FROM node:20-alpine AS frontend-builder
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------- Stage 2: runtime -----------------------------------------------
FROM python:3.11-slim AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System libraries required by opencv-python-headless / Pillow / EasyOCR.
# curl is needed for the container HEALTHCHECK.
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies (requirements.txt is pinned per SPEC 1.8).
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# spaCy English model (Layer 2 NER). Installed from the pinned pre-built
# wheel release so no network call happens at container start.
RUN pip install --no-cache-dir \
    https://github.com/explosion/spacy-models/releases/download/en_core_web_sm-3.8.0/en_core_web_sm-3.8.0-py3-none-any.whl

# Application code.
COPY backend/ ./backend/

# Built SPA. backend/main.py serves this directory via
# StaticFiles(directory="/app/static", html=True) mounted at "/".
COPY --from=frontend-builder /build/frontend/dist /app/static

# Persistent data (SQLite DB + stored originals/masked outputs).
# Mount a volume at /app/data (see docker-compose.yml).
ENV DATA_DIR=/app/data
RUN mkdir -p /app/data

WORKDIR /app/backend
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s --retries=3 \
    CMD curl -fsS http://localhost:8000/api/v1/health || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
