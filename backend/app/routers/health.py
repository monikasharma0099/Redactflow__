"""Health endpoint (SPEC 1.3). Open even when API_KEY is set."""

import importlib.util
import logging

from fastapi import APIRouter

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


def _ollama_available() -> bool:
    if not settings.ENABLE_LLM:
        return False
    try:
        import requests

        resp = requests.get(f"{settings.OLLAMA_HOST}/api/tags", timeout=1)
        return resp.status_code == 200
    except Exception:
        return False


def _spacy_available() -> bool:
    if not settings.ENABLE_SPACY:
        return False
    try:
        if importlib.util.find_spec("spacy") is None:
            return False
        return importlib.util.find_spec(settings.SPACY_MODEL) is not None
    except Exception:
        return False


@router.get("/health")
def health():
    return {
        "status": "ok",
        "ollama": _ollama_available(),
        "spacy": _spacy_available(),
        "version": settings.VERSION,
    }
