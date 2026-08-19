"""Security helpers: magic-byte sniffing, filename sanitization, API-key auth."""

import re
from typing import Optional

from fastapi import Header, HTTPException

from app.core.config import settings

# Magic byte signatures for supported uploads.
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"
PDF_MAGIC = b"%PDF"


def sniff_file_type(data: bytes) -> Optional[str]:
    """Return 'png', 'jpeg' or 'pdf' based on magic bytes, else None.

    Content-Type headers are client-controlled and never trusted.
    """
    if data[:8] == PNG_MAGIC:
        return "png"
    if data[:3] == JPEG_MAGIC:
        return "jpeg"
    if data[:4] == PDF_MAGIC:
        return "pdf"
    return None


_FILENAME_SAFE = re.compile(r"[^A-Za-z0-9._-]")


def sanitize_filename(filename: Optional[str], max_length: int = 100) -> str:
    """Werkzeug-style sanitization: keep [A-Za-z0-9._-], cap at 100 chars."""
    if not filename:
        return "upload"
    name = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    name = _FILENAME_SAFE.sub("_", name).strip("._") or "upload"
    return name[:max_length]


async def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    """FastAPI dependency enforcing X-API-Key when settings.API_KEY is set.

    When API_KEY is unset the API is open (documented behavior, SPEC 1.7).
    """
    expected = settings.API_KEY
    if not expected:
        return
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
