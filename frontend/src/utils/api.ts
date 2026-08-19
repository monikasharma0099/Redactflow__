import axios from 'axios';
import type {
  BatchResponse,
  BatchStatus,
  HealthStatus,
  HistoryItem,
  PDFResponse,
  ProcessResponse,
  RemaskRequest,
} from '../types';

const API_KEY_STORAGE_KEY = 'redactflow_api_key';

export const getApiKey = (): string =>
  localStorage.getItem(API_KEY_STORAGE_KEY) ?? '';

export const setApiKey = (key: string): void => {
  if (key) {
    localStorage.setItem(API_KEY_STORAGE_KEY, key);
  } else {
    localStorage.removeItem(API_KEY_STORAGE_KEY);
  }
};

const api = axios.create({
  baseURL: '/api/v1',
  // 120s for process/batch uploads (OCR can be slow)
  timeout: 120_000,
});

// Attach the optional API key (backend only enforces it when API_KEY is set).
api.interceptors.request.use((config) => {
  const key = getApiKey();
  if (key) {
    config.headers.set('X-API-Key', key);
  }
  return config;
});

/** Extract a human-readable message from an API error ({detail: "..."}). */
export const getErrorMessage = (err: unknown): string => {
  if (axios.isCancel(err)) {
    return 'Request cancelled';
  }
  if (axios.isAxiosError(err)) {
    const detail: unknown = err.response?.data?.detail;
    if (typeof detail === 'string') return detail;
    if (err.code === 'ECONNABORTED') {
      return 'Request timed out — the document may be too large or the backend is busy.';
    }
    if (err.response) {
      return `Request failed (${err.response.status})`;
    }
    return 'Cannot reach the backend. Is the server running?';
  }
  return 'An unexpected error occurred.';
};

/** Base64 payloads come without a data-url prefix — add one for <img>. */
export const toDataUrl = (base64: string): string =>
  base64.startsWith('data:') ? base64 : `data:image/png;base64,${base64}`;

/** Trigger a browser download for a Blob. */
export const saveBlob = (blob: Blob, filename: string): void => {
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);
};

export const healthCheck = async (signal?: AbortSignal): Promise<HealthStatus> => {
  const response = await api.get<HealthStatus>('/health', { signal });
  return response.data;
};

export const processImage = async (
  file: File,
  maskType: string,
  confidenceThreshold: number,
  signal?: AbortSignal,
): Promise<ProcessResponse> => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('mask_type', maskType);
  formData.append('confidence_threshold', String(confidenceThreshold));

  const response = await api.post<ProcessResponse>('/process', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    signal,
  });
  return response.data;
};

export const remaskJob = async (
  jobId: string,
  request: RemaskRequest,
  signal?: AbortSignal,
): Promise<ProcessResponse> => {
  const response = await api.post<ProcessResponse>(
    `/jobs/${jobId}/remask`,
    request,
    { signal },
  );
  return response.data;
};

/**
 * Download the STORED masked image for a job — never re-runs the pipeline,
 * so the downloaded file always matches the on-screen preview.
 */
export const downloadJobImage = async (
  jobId: string,
  signal?: AbortSignal,
): Promise<Blob> => {
  const response = await api.get<Blob>(`/jobs/${jobId}/download`, {
    responseType: 'blob',
    signal,
  });
  return response.data;
};

export const createBatch = async (
  files: File[],
  maskType: string,
  signal?: AbortSignal,
): Promise<BatchResponse> => {
  const formData = new FormData();
  files.forEach((file) => formData.append('files', file));
  formData.append('mask_type', maskType);

  const response = await api.post<BatchResponse>('/batch', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    signal,
  });
  return response.data;
};

export const getBatchStatus = async (
  batchId: string,
  signal?: AbortSignal,
): Promise<BatchStatus> => {
  const response = await api.get<BatchStatus>(`/batch/${batchId}`, { signal });
  return response.data;
};

export const downloadBatchZip = async (
  batchId: string,
  signal?: AbortSignal,
): Promise<Blob> => {
  const response = await api.get<Blob>(`/batch/${batchId}/download`, {
    responseType: 'blob',
    signal,
  });
  return response.data;
};

export const processPDF = async (
  file: File,
  maskType: string,
  signal?: AbortSignal,
): Promise<PDFResponse> => {
  const formData = new FormData();
  formData.append('file', file);
  formData.append('mask_type', maskType);

  const response = await api.post<PDFResponse>('/pdf', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    // PDF rendering + per-page OCR can take minutes
    timeout: 300_000,
    signal,
  });
  return response.data;
};

export const getHistory = async (signal?: AbortSignal): Promise<HistoryItem[]> => {
  const response = await api.get<HistoryItem[]>('/history', { signal });
  return response.data;
};

export const deleteHistoryItem = async (
  jobId: string,
  signal?: AbortSignal,
): Promise<void> => {
  await api.delete(`/history/${jobId}`, { signal });
};
