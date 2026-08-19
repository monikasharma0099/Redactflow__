"""SQLite persistence via SQLAlchemy 2.0 (SPEC 1.4).

Database lives at DATA_DIR/redactflow.db (env DATA_DIR, default ./data).
Engines are cached per resolved path so tests can point DATA_DIR at a
temporary directory. `cleanup_old_jobs(days=7)` is callable directly and
is also invoked on application startup.
"""

import logging
import shutil
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from sqlalchemy import create_engine, delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.models.db_models import Base, Batch, Detection, Job

logger = logging.getLogger(__name__)


def data_dir() -> Path:
    p = Path(settings.DATA_DIR).resolve()
    p.mkdir(parents=True, exist_ok=True)
    return p


def storage_dir() -> Path:
    p = data_dir() / "storage"
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path() -> Path:
    return data_dir() / "redactflow.db"


@lru_cache(maxsize=8)
def _engine_for(path: str):
    return create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})


def get_engine():
    return _engine_for(str(db_path()))


def get_session() -> Session:
    factory = sessionmaker(bind=get_engine(), expire_on_commit=False)
    return factory()


def init_db() -> None:
    Base.metadata.create_all(get_engine())


def job_storage(job_id: str) -> Path:
    p = storage_dir() / job_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def cleanup_old_jobs(days: int = 7) -> int:
    """Delete jobs (and their artifacts) older than `days`. Returns count."""
    init_db()
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    removed = 0
    with get_session() as session:
        old_jobs = session.execute(select(Job).where(Job.created_at < cutoff)).scalars().all()
        for job in old_jobs:
            session.execute(delete(Detection).where(Detection.job_id == job.id))
            session.delete(job)
            shutil.rmtree(storage_dir() / job.id, ignore_errors=True)
            removed += 1
        old_batches = session.execute(select(Batch).where(Batch.created_at < cutoff)).scalars().all()
        for batch in old_batches:
            if batch.zip_path:
                Path(batch.zip_path).unlink(missing_ok=True)
            session.delete(batch)
        session.commit()
    if removed:
        logger.info("TTL cleanup removed %d jobs older than %d days", removed, days)
    return removed
