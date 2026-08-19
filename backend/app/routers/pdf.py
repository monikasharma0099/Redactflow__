"""PDF endpoint: per-page pipeline at 150 DPI, real measured timing."""

import logging
import time

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.core.config import settings
from app.core.rate_limit import limiter
from app.core.security import require_api_key, sanitize_filename, sniff_file_type
from app.models.schemas import PDFPageResult, PDFResponse
from app.services import job_service, pdf_service
from app.services.job_service import run_pipeline
from app.services.ocr_service import get_ocr_service

logger = logging.getLogger(__name__)

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.post("/pdf", response_model=PDFResponse)
@limiter.limit("30/minute")
def process_pdf(
    request: Request,
    file: UploadFile = File(...),
    mask_type: str = Form(default="blur"),
    ocr=Depends(get_ocr_service),
):
    data = file.file.read()
    if len(data) > settings.MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")
    if sniff_file_type(data) != "pdf":
        raise HTTPException(status_code=415, detail="Only PDF files are supported")

    start = time.perf_counter()
    try:
        pages = pdf_service.render_pages(data)  # 150 DPI, enforces MAX_PDF_PAGES
    except pdf_service.PDFPageLimitExceeded:
        raise HTTPException(
            status_code=413,
            detail=f"PDF exceeds page limit ({settings.MAX_PDF_PAGES} pages)",
        )
    except Exception:
        logger.warning("PDF render failed for %s", sanitize_filename(file.filename))
        raise HTTPException(status_code=400, detail="Invalid or corrupt PDF file")

    results = []
    total_pii = 0
    all_detections = []
    try:
        for i, page_img in enumerate(pages, start=1):
            detections, masked = run_pipeline(page_img, mask_type, 0.0, ocr)
            total_pii += len(detections)
            all_detections.extend(detections)
            results.append(
                PDFPageResult(
                    page_number=i,
                    detections=detections,
                    masked_image_base64=job_service.image_to_base64(masked),
                    original_image_base64=job_service.image_to_base64(page_img),
                )
            )
    except Exception:
        logger.exception("PDF pipeline failed")
        raise HTTPException(status_code=500, detail="PDF processing failed")
    elapsed_ms = (time.perf_counter() - start) * 1000.0

    job = job_service.create_job(
        kind="pdf",
        filename=sanitize_filename(file.filename),
        mask_type=mask_type,
        original=pages[0],
        masked=job_service.base64_to_image(results[0].masked_image_base64),
        detections=all_detections,
        processing_time_ms=elapsed_ms,
    )
    return PDFResponse(
        job_id=job.id,
        total_pages=len(pages),
        processed_pages=len(results),
        pages=results,
        total_pii_found=total_pii,
        processing_time_ms=round(elapsed_ms, 2),
    )
