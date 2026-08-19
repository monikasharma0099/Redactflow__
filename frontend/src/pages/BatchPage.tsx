import { useState, useCallback, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import {
  Layers,
  CheckCircle,
  XCircle,
  Loader,
  FileImage,
  Download,
  Clock,
} from 'lucide-react';
import axios from 'axios';
import { DropZone } from '../components/DropZone';
import { MaskSelector } from '../components/MaskSelector';
import { ErrorBanner } from '../components/ErrorBanner';
import {
  createBatch,
  getBatchStatus,
  downloadBatchZip,
  getErrorMessage,
  saveBlob,
} from '../utils/api';
import type { BatchStatus, MaskType } from '../types';

const MAX_BATCH_FILES = 20;
const POLL_INTERVAL_MS = 2000;

export const BatchPage = () => {
  const [files, setFiles] = useState<File[]>([]);
  const [maskType, setMaskType] = useState<MaskType>('blur');
  const [submitting, setSubmitting] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [batch, setBatch] = useState<BatchStatus | null>(null);
  const [error, setError] = useState<string | null>(null);

  const pollTimer = useRef<number | null>(null);
  const requestCtrl = useRef<AbortController | null>(null);

  const stopPolling = useCallback(() => {
    if (pollTimer.current !== null) {
      window.clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
  }, []);

  // Stop polling / cancel requests on unmount.
  useEffect(() => {
    return () => {
      stopPolling();
      requestCtrl.current?.abort();
    };
  }, [stopPolling]);

  const schedulePoll = useCallback(
    (batchId: string) => {
      stopPolling();
      pollTimer.current = window.setTimeout(async () => {
        try {
          const status = await getBatchStatus(batchId);
          setBatch(status);
          if (status.status === 'completed' || status.status === 'failed') {
            stopPolling();
          } else {
            schedulePoll(batchId);
          }
        } catch (err) {
          stopPolling();
          setError(getErrorMessage(err));
        }
      }, POLL_INTERVAL_MS);
    },
    [stopPolling],
  );

  const handleFileSelect = useCallback(
    (selected: File[]) => {
      setError(null);
      setBatch(null);
      stopPolling();
      if (selected.length > MAX_BATCH_FILES) {
        setError(
          `You selected ${selected.length} files — the maximum is ${MAX_BATCH_FILES}. Only the first ${MAX_BATCH_FILES} were kept.`,
        );
        setFiles(selected.slice(0, MAX_BATCH_FILES));
      } else {
        setFiles(selected);
      }
    },
    [stopPolling],
  );

  const handleProcess = useCallback(async () => {
    if (files.length === 0) return;
    requestCtrl.current?.abort();
    const ctrl = new AbortController();
    requestCtrl.current = ctrl;
    setSubmitting(true);
    setError(null);
    setBatch(null);
    try {
      const created = await createBatch(files, maskType, ctrl.signal);
      // Show an initial status immediately, then poll until done.
      setBatch({
        batch_id: created.batch_id,
        status: created.status,
        total_files: created.total_files,
        processed: 0,
        failed: 0,
        items: [],
      });
      schedulePoll(created.batch_id);
    } catch (err) {
      if (!axios.isCancel(err)) setError(getErrorMessage(err));
    } finally {
      if (requestCtrl.current === ctrl) setSubmitting(false);
    }
  }, [files, maskType, schedulePoll]);

  const handleDownloadZip = useCallback(async () => {
    if (!batch) return;
    setDownloading(true);
    setError(null);
    try {
      const blob = await downloadBatchZip(batch.batch_id);
      saveBlob(blob, `redactflow_batch_${batch.batch_id.slice(0, 8)}.zip`);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setDownloading(false);
    }
  }, [batch]);

  const running =
    batch !== null && batch.status !== 'completed' && batch.status !== 'failed';
  const progress =
    batch && batch.total_files > 0
      ? ((batch.processed + batch.failed) / batch.total_files) * 100
      : 0;

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="text-center animate-slide-up">
        <h2 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
          Batch Processing
        </h2>
        <p className="text-gray-600 dark:text-gray-400">
          Redact up to {MAX_BATCH_FILES} images in one run, then download everything as a ZIP.
        </p>
      </div>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      <div className="glass-panel p-6">
        <h3 className="text-lg font-semibold mb-4 text-gray-800 dark:text-white">
          Batch Upload
        </h3>
        <DropZone
          onFileSelect={handleFileSelect}
          onReject={setError}
          multiple
          maxFiles={MAX_BATCH_FILES}
        />
        {files.length > 0 && (
          <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} className="mt-4 space-y-2">
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
              {files.length} file(s) selected
            </p>
            <div className="flex flex-wrap gap-2">
              {files.map((f, i) => (
                <span
                  key={`${f.name}-${i}`}
                  className="inline-flex items-center gap-1 px-2 py-1 bg-gray-100 dark:bg-dark-700 rounded text-xs text-gray-600 dark:text-gray-400"
                >
                  <FileImage className="w-3 h-3" />
                  {f.name}
                </span>
              ))}
            </div>
          </motion.div>
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
        disabled={files.length === 0 || submitting || running}
        className="w-full btn-primary flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
      >
        {submitting || running ? (
          <Loader className="w-5 h-5 animate-spin" />
        ) : (
          <Layers className="w-5 h-5" />
        )}
        {submitting
          ? 'Uploading…'
          : running
            ? 'Batch processing…'
            : 'Process Batch'}
      </button>

      {batch && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-panel p-6"
        >
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-semibold text-gray-800 dark:text-white">
              Batch Progress
            </h3>
            <span className="text-xs font-mono text-gray-400">
              ID: {batch.batch_id.slice(0, 8)} • {batch.status}
            </span>
          </div>

          <div className="mb-4">
            <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400 mb-1">
              <span>
                {batch.processed + batch.failed} / {batch.total_files} files
              </span>
              <span>{progress.toFixed(0)}%</span>
            </div>
            <div className="w-full h-3 bg-gray-200 dark:bg-dark-700 rounded-full overflow-hidden">
              <div
                className={`h-full rounded-full transition-all duration-500 ${
                  batch.status === 'failed' ? 'bg-red-500' : 'bg-primary-600'
                }`}
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>

          {batch.items.length > 0 && (
            <div className="space-y-2 mb-4">
              {batch.items.map((item, idx) => (
                <div
                  key={`${item.filename}-${idx}`}
                  className="flex items-center justify-between p-3 bg-gray-50 dark:bg-dark-700/50 rounded-lg"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    {item.status === 'completed' ? (
                      <CheckCircle className="w-5 h-5 text-green-500 shrink-0" />
                    ) : item.status === 'failed' ? (
                      <XCircle className="w-5 h-5 text-red-500 shrink-0" />
                    ) : (
                      <Clock className="w-5 h-5 text-gray-400 shrink-0" />
                    )}
                    <div className="min-w-0">
                      <span className="block text-sm text-gray-700 dark:text-gray-300 truncate max-w-xs">
                        {item.filename}
                      </span>
                      {item.error && (
                        <span className="block text-xs text-red-500 truncate max-w-xs">
                          {item.error}
                        </span>
                      )}
                    </div>
                  </div>
                  <span className="text-xs font-medium text-gray-500 shrink-0">
                    {item.pii_count} detections
                  </span>
                </div>
              ))}
            </div>
          )}

          {batch.status === 'completed' && (
            <button
              onClick={() => void handleDownloadZip()}
              disabled={downloading}
              className="w-full btn-primary flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {downloading ? (
                <Loader className="w-5 h-5 animate-spin" />
              ) : (
                <Download className="w-5 h-5" />
              )}
              {downloading ? 'Preparing ZIP…' : 'Download ZIP'}
            </button>
          )}
        </motion.div>
      )}
    </div>
  );
};
