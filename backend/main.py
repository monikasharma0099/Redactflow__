"""
RedactFlow v2 — Intelligent Document Privacy Engine.

FastAPI backend for PII detection (regex + optional spaCy NER + optional
Ollama LLM), masking, synthetic replacement, batch processing and PDF
redaction. Importing this module never downloads models or touches heavy
dependencies — EasyOCR/spaCy are loaded lazily on first use.
"""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.database import cleanup_old_jobs, init_db
from app.core.rate_limit import limiter
from app.routers import batch, health, history, pdf, process

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("RedactFlow backend starting up...")
    init_db()
    cleanup_old_jobs(days=settings.JOB_TTL_DAYS)
    yield
    logger.info("RedactFlow backend shutting down...")


app = FastAPI(
    title="RedactFlow API",
    description="Document privacy engine: PII detection, masking, synthetic replacement.",
    version=settings.VERSION,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=False,  # SPEC 1.7
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

for r in (health.router, process.router, batch.router, pdf.router, history.router):
    app.include_router(r, prefix="/api/v1")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Never leak internal error details in 500 responses."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# Serve the built frontend when present (Docker image layout); the API
# always lives under /api/v1. SPA fallback: any non-API path that doesn't
# match a static file returns index.html so client-side routes (/batch,
# /pdf, /history) survive page refreshes and direct links.
_static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(_static_dir):
    from fastapi.responses import FileResponse, JSONResponse
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")

    @app.exception_handler(404)
    async def spa_fallback(request, exc):
        if not request.url.path.startswith("/api/"):
            index = os.path.join(_static_dir, "index.html")
            if os.path.isfile(index):
                return FileResponse(index)
        return JSONResponse({"detail": "Not Found"}, status_code=404)
else:

    @app.get("/")
    async def root():
        return {
            "name": settings.APP_NAME,
            "version": settings.VERSION,
            "description": "Intelligent Document Privacy Engine",
            "docs": "/docs",
        }
