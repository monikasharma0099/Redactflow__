import { useState, useCallback, useEffect, useRef } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  FileText,
  Loader,
  ChevronLeft,
  ChevronRight,
  Clock,
  CheckCircle,
} from 'lucide-react';
import axios from 'axios';
import { DropZone } from '../components/DropZone';
import { MaskSelector } from '../components/MaskSelector';
import { ErrorBanner } from '../components/ErrorBanner';
import { processPDF, getErrorMessage, toDataUrl } from '../utils/api';
import type { MaskType, PDFResponse } from '../types';

export const PDFPage = () => {
  const [file, setFile] = useState<File | null>(null);
  const [maskType, setMaskType] = useState<MaskType>('blur');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PDFResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pageIndex, setPageIndex] = useState(0);
  const [side, setSide] = useState<'before' | 'after'>('after');

  const requestCtrl = useRef<AbortController | null>(null);

  // Cancel the in-flight PDF request when leaving the page.
  useEffect(() => {
    return () => requestCtrl.current?.abort();
  }, []);

  const handleFileSelect = useCallback((files: File[]) => {
    const selected = files[0];
    if (!selected) return;
    // Explicit MIME validation — never accept a wrong file type silently.
    if (selected.type !== 'application/pdf') {
      setError(`"${selected.name}" is not a PDF (application/pdf). Please choose a PDF file.`);
      setFile(null);
      return;
    }
    // New upload cancels any previous in-flight request.
    requestCtrl.current?.abort();
    setFile(selected);
    setResult(null);
    setError(null);
    setPageIndex(0);
    setSide('after');
  }, []);

  const handleProcess = useCallback(async () => {
    if (!file) return;
    requestCtrl.current?.abort();
    const ctrl = new AbortController();
    requestCtrl.current = ctrl;
    setLoading(true);
    setError(null);
    try {
      const response = await processPDF(file, maskType, ctrl.signal);
      setResult(response);
      setPageIndex(0);
      setSide('after');
    } catch (err) {
      if (!axios.isCancel(err)) setError(getErrorMessage(err));
    } finally {
      if (requestCtrl.current === ctrl) setLoading(false);
    }
  }, [file, maskType]);

  const page = result?.pages[pageIndex] ?? null;

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="text-center animate-slide-up">
        <h2 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
          PDF Redaction
        </h2>
        <p className="text-gray-600 dark:text-gray-400">
          Each page is rendered, scanned for PII, and masked — compare before/after page by page.
        </p>
      </div>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      <div className="glass-panel p-6">
        <h3 className="text-lg font-semibold mb-4 text-gray-800 dark:text-white">
          Upload PDF
        </h3>
        <DropZone onFileSelect={handleFileSelect} onReject={setError} accept="pdf" />
        {file && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="mt-3 text-sm text-gray-600 dark:text-gray-400 flex items-center gap-2"
          >
            <FileText className="w-4 h-4" />
            {file.name}
          </motion.p>
        )}
      </div>

      <div className="glass-panel p-6">
        <h3 className="text-lg font-semibold mb-4 text-gray-800 dark:text-white">
          Masking Style
        </h3>
        <MaskSelector selected={maskType} onChange={setMaskType} />
      </div>

      <button
        onClick={() => void handleProcess()}
        disabled={!file || loading}
        className="w-full btn-primary flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {loading ? <Loader className="w-5 h-5 animate-spin" /> : <FileText className="w-5 h-5" />}
        {loading ? 'Processing PDF (pages are OCR’d one by one)…' : 'Process PDF'}
      </button>

      {result && (
        <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="glass-panel p-6">
          <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
            <h3 className="text-lg font-semibold text-gray-800 dark:text-white">
              Results: {result.processed_pages}/{result.total_pages} pages
            </h3>
            <div className="flex items-center gap-3">
              <span className="px-3 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded-full text-sm font-medium flex items-center gap-1">
                <CheckCircle className="w-4 h-4" />
                {result.total_pii_found} PII found
              </span>
              <span className="flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400">
                <Clock className="w-4 h-4" />
                {(result.processing_time_ms / 1000).toFixed(1)}s
              </span>
            </div>
          </div>

          {page && (
            <div>
              {/* Carousel controls */}
              <div className="flex items-center justify-between mb-3">
                <button
                  onClick={() => setPageIndex((i) => Math.max(0, i - 1))}
                  disabled={pageIndex === 0}
                  className="p-2 rounded-lg bg-gray-100 dark:bg-dark-700 hover:bg-gray-200 dark:hover:bg-dark-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  aria-label="Previous page"
                >
                  <ChevronLeft className="w-5 h-5 text-gray-700 dark:text-gray-300" />
                </button>

                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
                    Page {page.page_number} of {result.pages.length}
                  </span>
                  <span className="text-xs px-2 py-1 bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400 rounded-full">
                    {page.detections.length} PII items
                  </span>
                </div>

                <button
                  onClick={() => setPageIndex((i) => Math.min(result.pages.length - 1, i + 1))}
                  disabled={pageIndex >= result.pages.length - 1}
                  className="p-2 rounded-lg bg-gray-100 dark:bg-dark-700 hover:bg-gray-200 dark:hover:bg-dark-600 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                  aria-label="Next page"
                >
                  <ChevronRight className="w-5 h-5 text-gray-700 dark:text-gray-300" />
                </button>
              </div>

              {/* Before/after toggle */}
              <div className="flex justify-center mb-3">
                <div className="inline-flex bg-gray-100 dark:bg-dark-700 rounded-lg p-1">
                  {(['before', 'after'] as const).map((s) => (
                    <button
                      key={s}
                      onClick={() => setSide(s)}
                      className={`px-4 py-1.5 rounded-md text-sm font-medium transition-all ${
                        side === s
                          ? 'bg-primary-600 text-white shadow'
                          : 'text-gray-600 dark:text-gray-400'
                      }`}
                    >
                      {s === 'before' ? 'Before' : 'After'}
                    </button>
                  ))}
                </div>
              </div>

              <AnimatePresence mode="wait">
                <motion.img
                  key={`${page.page_number}-${side}`}
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  transition={{ duration: 0.2 }}
                  src={toDataUrl(
                    side === 'before'
                      ? page.original_image_base64
                      : page.masked_image_base64,
                  )}
                  alt={`Page ${page.page_number} (${side})`}
                  className="w-full max-h-[32rem] object-contain rounded-lg border border-gray-200 dark:border-dark-700 bg-gray-100 dark:bg-dark-900"
                />
              </AnimatePresence>

              {/* Page dots */}
              <div className="flex justify-center gap-1.5 mt-4 flex-wrap">
                {result.pages.map((p, i) => (
                  <button
                    key={p.page_number}
                    onClick={() => setPageIndex(i)}
                    aria-label={`Go to page ${p.page_number}`}
                    className={`w-2.5 h-2.5 rounded-full transition-colors ${
                      i === pageIndex
                        ? 'bg-primary-600'
                        : 'bg-gray-300 dark:bg-dark-600 hover:bg-primary-400'
                    }`}
                  />
                ))}
              </div>
            </div>
          )}
        </motion.div>
      )}
    </div>
  );
};
