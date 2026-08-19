"""Image processing endpoints: /process, /jobs/{id}/remask, /jobs/{id}/download.

`def` endpoints: FastAPI runs them in a threadpool, so blocking OCR/LLM
work never stalls the event loop (SPEC 1.3).
"""

import io
import logging
import time

from fastapi import (APIRouter, Depends, File, Form, HTTPException, Request,
                     UploadFile)
from fastapi.responses import FileResponse
from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.security import require_api_key, sanitize_filename, sniff_file_type
from app.models.schemas import ProcessResponse, RemaskRequest
from app.services import job_service
from app.services.job_service import run_pipeline
from app.services.masking_service import get_masking_service
from app.services.ocr_service import get_ocr_service

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_api_key)])


def _read_image_upload(data: bytes) -> Image.Image:
    if len(data) > settings.MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
    if sniff_file_type(data) not in ("png", "jpeg"):
        raise HTTPException(status_code=415, detail="Only PNG and JPEG images are supported")
    try:
        return Image.open(io.BytesIO(data)).convert("RGB")
    except (UnidentifiedImageError, OSError):
        raise HTTPException(status_code=400, detail="Corrupt or unreadable image file")


@router.post("/process", response_model=ProcessResponse)
@limiter.limit("30/minute")
def process_image(
    request: Request,
    file: UploadFile = File(...),
    mask_type: str = Form(default="blur"),
    confidence_threshold: float = Form(default=0.0),
    ocr=Depends(get_ocr_service),
):
    data = file.file.read()
    image = _read_image_upload(data)
    filename = sanitize_filename(file.filename)

    start = time.perf_counter()
    try:
        detections, masked = run_pipeline(image, mask_type, confidence_threshold, ocr)
    except HTTPException:
        raise
    except Exception:
        logger.exception("Processing pipeline failed")
        raise HTTPException(status_code=500, detail="Image processing failed")
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    job = job_service.create_job(
        kind="image",
        filename=filename,
        mask_type=mask_type,
        original=image,
        masked=masked,
        detections=detections,
        processing_time_ms=elapsed_ms,
    )
    return ProcessResponse(
        job_id=job.id,
        detections=detections,
        pii_count=len(detections),
        masked_image_base64=job_service.image_to_base64(masked),
        original_image_base64=job_service.image_to_base64(image),
        processing_time_ms=round(elapsed_ms, 2),
    )


@router.post("/jobs/{job_id}/remask", response_model=ProcessResponse)
@limiter.limit("30/minute")
def remask_job(request: Request, job_id: str, body: RemaskRequest):
    """Re-mask the STORED original with STORED detections (no OCR/LLM re-run)."""
    job = job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    start = time.perf_counter()
    original = job_service.load_job_image(job, "original")
    stored = job_service.get_job_detections(job_id)
    excluded = set(body.excluded_detection_ids)
    to_mask = [
        d for d in stored
        if d.id not in excluded and d.confidence >= body.confidence_threshold
    ]
    try:
        masked = get_masking_service().apply_mask(original, to_mask, body.mask_type)
    except Exception:
        logger.exception("Remask failed for job %s", job_id)
        raise HTTPException(status_code=500, detail="Remask failed")
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    job_service.update_job_masked(job_id, masked, body.mask_type, len(to_mask), elapsed_ms)

    masked_ids = {d.id for d in to_mask}
    for det in stored:
        if det.id not in masked_ids:
            det.masked_text = None
    return ProcessResponse(
        job_id=job_id,
        detections=stored,
        pii_count=len(to_mask),
        masked_image_base64=job_service.image_to_base64(masked),
        original_image_base64=job_service.image_to_base64(original),
        processing_time_ms=round(elapsed_ms, 2),
    )


@router.get("/jobs/{job_id}/download")
def download_job(job_id: str):
    """Stream the stored masked PNG — no re-processing."""
    job = job_service.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    filename = sanitize_filename(f"{job.filename.rsplit('.', 1)[0]}_masked.png")
    return FileResponse(job.masked_path, media_type="image/png", filename=filename)
