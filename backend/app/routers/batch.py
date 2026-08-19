"""Batch endpoints: real BackgroundTasks lifecycle with DB status + zip."""

import logging
from pathlib import Path
from typing import List

from fastapi import (APIRouter, BackgroundTasks, Depends, File, Form,
                     HTTPException, Request, UploadFile)
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.core.database import storage_dir
from app.core.rate_limit import limiter
from app.core.security import require_api_key, sanitize_filename, sniff_file_type
from app.models.schemas import BatchItem, BatchResponse, BatchStatus
from app.services import job_service
from app.services.job_service import run_pipeline

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_api_key)])


def _process_batch(batch_id: str, upload_dir: Path, filenames: List[str], mask_type: str):
    """Background worker: queued -> processing -> completed/failed."""
    job_service.update_batch(batch_id, status="processing")
    processed = failed = 0
    for filename in filenames:
        safe = sanitize_filename(filename)
        try:
            data = (upload_dir / safe).read_bytes()
            if sniff_file_type(data) not in ("png", "jpeg"):
                raise ValueError("unsupported file type")
            import io

            image = Image.open(io.BytesIO(data)).convert("RGB")
            detections, masked = run_pipeline(image, mask_type)
            job_service.create_job(
                kind="batch_item", filename=safe, mask_type=mask_type,
                original=image, masked=masked, detections=detections,
                batch_id=batch_id, status="completed",
            )
            processed += 1
        except (UnidentifiedImageError, OSError, ValueError) as exc:
            logger.warning("Batch item %s failed: %s", safe, type(exc).__name__)
            job_service.create_job(
                kind="batch_item", filename=safe, mask_type=mask_type,
                original=Image.new("RGB", (1, 1), (0, 0, 0)), detections=[],
                batch_id=batch_id, status="failed", error="processing failed",
            )
            failed += 1
        except Exception:
            logger.exception("Batch item %s failed unexpectedly", safe)
            failed += 1
        job_service.update_batch(batch_id, processed=processed, failed=failed)

    items = job_service.get_batch_items(batch_id)
    zip_path = job_service.build_batch_zip(batch_id, items)
    job_service.update_batch(batch_id, status="completed", zip_path=zip_path)
    logger.info("Batch %s completed: %d processed, %d failed", batch_id, processed, failed)


@router.post("/batch", response_model=BatchResponse)
@limiter.limit("30/minute")
def create_batch(
    request: Request,
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    mask_type: str = Form(default="blur"),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    if len(files) > settings.BATCH_MAX_FILES:
        raise HTTPException(
            status_code=413,
            detail=f"Too many files (max {settings.BATCH_MAX_FILES})",
        )

    batch = job_service.create_batch(total_files=len(files), mask_type=mask_type)
    upload_dir = storage_dir() / f"batch_{batch.id}_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    filenames: List[str] = []
    for f in files:
        data = f.file.read()
        if len(data) > settings.MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
        safe = sanitize_filename(f.filename)
        (upload_dir / safe).write_bytes(data)
        filenames.append(safe)

    background_tasks.add_task(_process_batch, batch.id, upload_dir, filenames, mask_type)
    return BatchResponse(batch_id=batch.id, total_files=len(files), status="queued")


@router.get("/batch/{batch_id}", response_model=BatchStatus)
def batch_status(batch_id: str):
    batch = job_service.get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    items = [
        BatchItem(
            filename=job.filename,
            status=job.status,
            pii_count=job.pii_count,
            error=job.error,
        )
        for job in job_service.get_batch_items(batch_id)
    ]
    return BatchStatus(
        batch_id=batch.id,
        status=batch.status,
        total_files=batch.total_files,
        processed=batch.processed,
        failed=batch.failed,
        items=items,
    )


@router.get("/batch/{batch_id}/download")
def batch_download(batch_id: str):
    batch = job_service.get_batch(batch_id)
    if batch is None or batch.status != "completed" or not batch.zip_path:
        raise HTTPException(status_code=404, detail="Batch archive not ready")
    if not Path(batch.zip_path).exists():
        raise HTTPException(status_code=404, detail="Batch archive not ready")
    return FileResponse(batch.zip_path, media_type="application/zip",
                        filename=f"redactflow_batch_{batch_id[:8]}.zip")
