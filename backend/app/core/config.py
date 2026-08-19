"""Application configuration (SPEC 1.7).

All settings are overridable via environment variables or a .env file.
No heavy resources are created here — importing this module is cheap.
"""

from functools import lru_cache
from typing import List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    APP_NAME: str = "RedactFlow"
    VERSION: str = "2.0.0"
    DEBUG: bool = False

    # CORS (credentials are always disabled, SPEC 1.7)
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    # OCR settings (EasyOCR reader is created lazily on first use)
    OCR_LANGUAGES: List[str] = ["en"]
    OCR_GPU: bool = False

    # Detection layer toggles
    ENABLE_SPACY: bool = True
    ENABLE_LLM: bool = False
    SPACY_MODEL: str = "en_core_web_sm"

    # LLM (Ollama) settings — only used when ENABLE_LLM=true.
    # PII disclosure: when enabled, extracted text is sent to OLLAMA_HOST.
    OLLAMA_HOST: str = "http://localhost:11434"
    LLM_MODEL: str = "llama3.2:3b"
    LLM_TIMEOUT: int = 30  # seconds

    # Limits
    MAX_FILE_SIZE: int = 10 * 1024 * 1024  # 10 MB
    MAX_PDF_PAGES: int = 25
    BATCH_MAX_FILES: int = 20

    # Persistence
    DATA_DIR: str = "./data"
    JOB_TTL_DAYS: int = 7

    # Optional API key auth: when set, every /api/v1 endpoint except
    # /health requires the X-API-Key header. When unset, the API is open.
    API_KEY: Optional[str] = None

    # Masking
    DEFAULT_MASK_TYPE: str = "blur"

    # Synthetic data
    SYNTHETIC_LOCALE: str = "en_IN"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
