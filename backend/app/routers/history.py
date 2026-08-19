"""History endpoints: list last 50 jobs, delete a job + artifacts."""

from fastapi import APIRouter, Depends, HTTPException

from app.core.security import require_api_key
from app.models.schemas import HistoryItem
from app.services import job_service

router = APIRouter(dependencies=[Depends(require_api_key)])


@router.get("/history", response_model=list[HistoryItem])
def history():
    jobs = job_service.list_history(limit=50)
    return [
        HistoryItem(
            job_id=j.id,
            kind=j.kind,
            filename=j.filename,
            pii_count=j.pii_count,
            mask_type=j.mask_type,
            created_at=j.created_at.isoformat(),
        )
        for j in jobs
    ]


@router.delete("/history/{job_id}")
def delete_history_item(job_id: str):
    if not job_service.delete_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return {"detail": "deleted"}
