"""Job persistence service (SPEC 1.4): jobs, detections, batches, artifacts.

Original/masked images are stored under DATA_DIR/storage/{job_id}/.
"""

import base64
import io
import logging
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image
from sqlalchemy import select

from app.core.database import get_session, init_db, job_storage, storage_dir
from app.models.db_models import Batch, Detection, Job
from app.models.schemas import BoundingBox, PIIDetection

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# image <-> base64 helpers
# ---------------------------------------------------------------------------

def image_to_base64(image: Image.Image, fmt: str = "PNG") -> str:
    buf = io.BytesIO()
    image.convert("RGB").save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def base64_to_image(data: str) -> Image.Image:
    return Image.open(io.BytesIO(base64.b64decode(data))).convert("RGB")


# ---------------------------------------------------------------------------
# jobs
# ---------------------------------------------------------------------------

def create_job(
    kind: str,
    filename: str,
    mask_type: str,
    original: Image.Image,
    masked: Optional[Image.Image] = None,
    detections: Optional[List[PIIDetection]] = None,
    processing_time_ms: float = 0.0,
    batch_id: Optional[str] = None,
    status: str = "completed",
    error: Optional[str] = None,
) -> Job:
    """Persist a job row, its detections and its image artifacts."""
    init_db()
    detections = detections or []
    job_id = uuid.uuid4().hex
    jdir = job_storage(job_id)
    original_path = jdir / "original.png"
    original.convert("RGB").save(original_path, format="PNG")
    masked_path = jdir / "masked.png"
    (masked or original).convert("RGB").save(masked_path, format="PNG")

    job = Job(
        id=job_id,
        kind=kind,
        filename=filename,
        mask_type=mask_type,
        status=status,
        pii_count=len(detections),
        processing_time_ms=processing_time_ms,
        original_path=str(original_path),
        masked_path=str(masked_path),
        batch_id=batch_id,
        error=error,
    )
    with get_session() as session:
        session.add(job)
        for det in detections:
            session.add(_detection_row(job_id, det))
        session.commit()
        session.refresh(job)
        session.expunge(job)
    return job


def _detection_row(job_id: str, det: PIIDetection) -> Detection:
    b = det.bounding_box
    return Detection(
        id=det.id,
        job_id=job_id,
        pii_type=det.pii_type,
        text=det.text,
        x=b.x if b else None,
        y=b.y if b else None,
        w=b.width if b else None,
        h=b.height if b else None,
        confidence=det.confidence,
        source=det.source,
    )


def row_to_detection(row: Detection) -> PIIDetection:
    bbox = None
    if row.x is not None and row.y is not None and row.w is not None and row.h is not None:
        bbox = BoundingBox(x=row.x, y=row.y, width=row.w, height=row.h)
    return PIIDetection(
        id=row.id,
        pii_type=row.pii_type,
        text=row.text,
        bounding_box=bbox,
        confidence=row.confidence,
        source=row.source,
    )


def get_job(job_id: str) -> Optional[Job]:
    init_db()
    with get_session() as session:
        job = session.get(Job, job_id)
        if job:
            session.expunge(job)
        return job


def get_job_detections(job_id: str) -> List[PIIDetection]:
    init_db()
    with get_session() as session:
        rows = session.execute(
            select(Detection).where(Detection.job_id == job_id)
        ).scalars().all()
        return [row_to_detection(r) for r in rows]


def load_job_image(job: Job, which: str = "original") -> Image.Image:
    path = job.original_path if which == "original" else job.masked_path
    return Image.open(path).convert("RGB")


def save_masked_image(job_id: str, masked: Image.Image) -> str:
    path = job_storage(job_id) / "masked.png"
    masked.convert("RGB").save(path, format="PNG")
    return str(path)


def update_job_masked(job_id: str, masked: Image.Image, mask_type: str,
                      pii_count: int, processing_time_ms: float) -> None:
    path = save_masked_image(job_id, masked)
    with get_session() as session:
        job = session.get(Job, job_id)
        if job:
            job.masked_path = path
            job.mask_type = mask_type
            job.pii_count = pii_count
            job.processing_time_ms = processing_time_ms
            session.commit()


def list_history(limit: int = 50) -> List[Job]:
    init_db()
    with get_session() as session:
        jobs = session.execute(
            select(Job).order_by(Job.created_at.desc()).limit(limit)
        ).scalars().all()
        for j in jobs:
            session.expunge(j)
        return jobs


def delete_job(job_id: str) -> bool:
    init_db()
    with get_session() as session:
        job = session.get(Job, job_id)
        if not job:
            return False
        session.delete(job)  # detections cascade
        session.commit()
    shutil.rmtree(job_storage(job_id), ignore_errors=True)
    return True


# ---------------------------------------------------------------------------
# pipeline orchestration
# ---------------------------------------------------------------------------

def run_pipeline(
    image: Image.Image,
    mask_type: str,
    confidence_threshold: float = 0.0,
    ocr_service=None,
) -> Tuple[List[PIIDetection], Image.Image]:
    """OCR -> detect -> mask. Heavy work; call from `def` endpoints only."""
    from app.services.masking_service import get_masking_service
    from app.services.ocr_service import get_ocr_service
    from app.services.pii_detector import PIIDetector

    ocr = ocr_service or get_ocr_service()
    regions = ocr.extract_text(image)
    full_text = "\n".join(r["text"] for r in regions if r.get("text"))
    detector = PIIDetector()
    detections = detector.detect(full_text, regions)
    if confidence_threshold > 0:
        detections = [d for d in detections if d.confidence >= confidence_threshold]
    masked = get_masking_service().apply_mask(image, detections, mask_type)
    return detections, masked


# ---------------------------------------------------------------------------
# batches
# ---------------------------------------------------------------------------

def create_batch(total_files: int, mask_type: str) -> Batch:
    init_db()
    batch = Batch(id=uuid.uuid4().hex, status="queued",
                  total_files=total_files, mask_type=mask_type)
    with get_session() as session:
        session.add(batch)
        session.commit()
        session.refresh(batch)
        session.expunge(batch)
    return batch


def get_batch(batch_id: str) -> Optional[Batch]:
    init_db()
    with get_session() as session:
        batch = session.get(Batch, batch_id)
        if batch:
            session.expunge(batch)
        return batch


def update_batch(batch_id: str, **fields) -> None:
    with get_session() as session:
        batch = session.get(Batch, batch_id)
        if batch:
            for key, value in fields.items():
                setattr(batch, key, value)
            session.commit()


def get_batch_items(batch_id: str) -> List[Job]:
    init_db()
    with get_session() as session:
        jobs = session.execute(
            select(Job).where(Job.batch_id == batch_id).order_by(Job.created_at)
        ).scalars().all()
        for j in jobs:
            session.expunge(j)
        return jobs


def build_batch_zip(batch_id: str, items: List[Job]) -> str:
    """Zip the masked PNGs of all completed batch items. Returns zip path."""
    zip_path = storage_dir() / f"batch_{batch_id}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in items:
            if item.status == "completed" and Path(item.masked_path).exists():
                zf.write(item.masked_path, arcname=f"{Path(item.filename).stem}_masked.png")
    return str(zip_path)


def delete_batch(batch_id: str) -> None:
    batch = get_batch(batch_id)
    if batch and batch.zip_path:
        Path(batch.zip_path).unlink(missing_ok=True)
    with get_session() as session:
        b = session.get(Batch, batch_id)
        if b:
            session.delete(b)
            session.commit()
