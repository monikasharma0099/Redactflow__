/**
 * API types mirroring SPEC 1.2 (backend models/schemas.py) EXACTLY.
 * Do not diverge from the backend contract.
 */

export interface BoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export type PIISource = 'regex' | 'spacy' | 'llm';

export interface PIIDetection {
  /** uuid4 hex, stable for the job */
  id: string;
  /** email|phone|aadhaar|pan|credit_card|ip|dob|ssn|url|name|address|organization */
  pii_type: string;
  text: string;
  bounding_box: BoundingBox | null;
  confidence: number;
  source: PIISource | string;
  masked_text?: string | null;
}

export interface ProcessResponse {
  job_id: string;
  detections: PIIDetection[];
  pii_count: number;
  /** PNG base64 — always returned */
  masked_image_base64: string;
  original_image_base64: string;
  processing_time_ms: number;
}

export interface RemaskRequest {
  mask_type: string;
  excluded_detection_ids: string[];
  confidence_threshold: number;
}

export type BatchState = 'queued' | 'processing' | 'completed' | 'failed';

export interface BatchResponse {
  batch_id: string;
  total_files: number;
  status: BatchState | string;
}

export interface BatchItem {
  filename: string;
  status: string;
  pii_count: number;
  error?: string | null;
}

export interface BatchStatus {
  batch_id: string;
  status: BatchState | string;
  total_files: number;
  processed: number;
  failed: number;
  items: BatchItem[];
}

export interface PDFPageResult {
  page_number: number;
  detections: PIIDetection[];
  masked_image_base64: string;
  original_image_base64: string;
}

export interface PDFResponse {
  job_id: string;
  total_pages: number;
  processed_pages: number;
  pages: PDFPageResult[];
  total_pii_found: number;
  processing_time_ms: number;
}

export interface HistoryItem {
  job_id: string;
  kind: string;
  filename: string;
  pii_count: number;
  mask_type: string;
  created_at: string;
}

export interface HealthStatus {
  status: string;
  ollama: boolean;
  spacy: boolean;
  version: string;
}

export type MaskType =
  | 'blur'
  | 'pixelate'
  | 'blackbox'
  | 'redbox'
  | 'whitebox'
  | 'synthetic';
