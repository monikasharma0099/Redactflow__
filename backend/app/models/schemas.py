"""Pydantic API schemas — API CONTRACT (SPEC 1.2). Do not rename fields."""

from typing import List, Optional

from pydantic import BaseModel, Field

# Valid pii_type values:
#   email|phone|aadhaar|pan|credit_card|ip|dob|ssn|url|name|address|organization
# Valid source values: regex|spacy|llm


class BoundingBox(BaseModel):
    x: int
    y: int
    width: int
    height: int


class PIIDetection(BaseModel):
    id: str  # uuid4 hex, stable for the job
    pii_type: str
    text: str
    bounding_box: Optional[BoundingBox] = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    source: str  # regex|spacy|llm
    masked_text: Optional[str] = None


class ProcessResponse(BaseModel):
    job_id: str
    detections: List[PIIDetection]
    pii_count: int
    masked_image_base64: str  # PNG base64 — ALWAYS returned
    original_image_base64: str
    processing_time_ms: float  # measured with time.perf_counter


class RemaskRequest(BaseModel):
    mask_type: str
    excluded_detection_ids: List[str] = []
    confidence_threshold: float = 0.0


class BatchItem(BaseModel):
    filename: str
    status: str
    pii_count: int
    error: Optional[str] = None


class BatchResponse(BaseModel):
    batch_id: str
    total_files: int
    status: str  # queued|processing|completed|failed


class BatchStatus(BaseModel):
    batch_id: str
    status: str
    total_files: int
    processed: int
    failed: int
    items: List[BatchItem]


class PDFPageResult(BaseModel):
    page_number: int
    detections: List[PIIDetection]
    masked_image_base64: str
    original_image_base64: str


class PDFResponse(BaseModel):
    job_id: str
    total_pages: int
    processed_pages: int
    pages: List[PDFPageResult]
    total_pii_found: int
    processing_time_ms: float


class HistoryItem(BaseModel):
    job_id: str
    kind: str
    filename: str
    pii_count: int
    mask_type: str
    created_at: str
