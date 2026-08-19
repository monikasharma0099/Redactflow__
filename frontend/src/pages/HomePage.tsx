import { useState, useCallback, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { Download, CheckCircle, Clock, Shield, Loader, RefreshCw } from 'lucide-react';
import axios from 'axios';
import { DropZone } from '../components/DropZone';
import { MaskSelector } from '../components/MaskSelector';
import { DetectionList } from '../components/DetectionList';
import { ErrorBanner } from '../components/ErrorBanner';
import {
  processImage,
  remaskJob,
  downloadJobImage,
  getErrorMessage,
  saveBlob,
  toDataUrl,
} from '../utils/api';
import type { MaskType, ProcessResponse } from '../types';

interface RemaskParams {
  maskType: MaskType;
  threshold: number;
  excludedIds: ReadonlySet<string>;
}

export const HomePage = () => {
  const [file, setFile] = useState<File | null>(null);
  const [localPreview, setLocalPreview] = useState<string | null>(null);
  const [result, setResult] = useState<ProcessResponse | null>(null);
  const [excludedIds, setExcludedIds] = useState<Set<string>>(new Set());
  const [maskType, setMaskType] = useState<MaskType>('blur');
  const [threshold, setThreshold] = useState(0);
  const [processing, setProcessing] = useState(false);
  const [remasking, setRemasking] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const processCtrl = useRef<AbortController | null>(null);
  const remaskCtrl = useRef<AbortController | null>(null);
  const sliderTimer = useRef<number | null>(null);

  // Cancel in-flight requests when leaving the page.
  useEffect(() => {
    return () => {
      processCtrl.current?.abort();
      remaskCtrl.current?.abort();
      if (sliderTimer.current !== null) window.clearTimeout(sliderTimer.current);
    };
  }, []);

  const runProcess = useCallback(
    async (selected: File, mask: MaskType, conf: number) => {
      processCtrl.current?.abort();
      remaskCtrl.current?.abort();
      const ctrl = new AbortController();
      processCtrl.current = ctrl;
      setProcessing(true);
      setError(null);
      try {
        const response = await processImage(selected, mask, conf, ctrl.signal);
        setResult(response);
        setExcludedIds(new Set());
      } catch (err) {
        if (!axios.isCancel(err)) setError(getErrorMessage(err));
      } finally {
        if (processCtrl.current === ctrl) setProcessing(false);
      }
    },
    [],
  );

  const runRemask = useCallback(
    async (params: RemaskParams) => {
      if (!result) return;
      remaskCtrl.current?.abort();
      const ctrl = new AbortController();
      remaskCtrl.current = ctrl;
      setRemasking(true);
      setError(null);
      try {
        const response = await remaskJob(
          result.job_id,
          {
            mask_type: params.maskType,
            excluded_detection_ids: [...params.excludedIds],
            confidence_threshold: params.threshold,
          },
          ctrl.signal,
        );
        setResult(response);
      } catch (err) {
        if (!axios.isCancel(err)) setError(getErrorMessage(err));
      } finally {
        if (remaskCtrl.current === ctrl) setRemasking(false);
      }
    },
    [result],
  );

  const handleFileSelect = useCallback(
    (files: File[]) => {
      const selected = files[0];
      if (!selected) return;
      // New upload cancels any in-flight request (AbortController).
      setFile(selected);
      setResult(null);
      setExcludedIds(new Set());
      setError(null);
      const reader = new FileReader();
      reader.onloadend = () => setLocalPreview(reader.result as string);
      reader.readAsDataURL(selected);
      void runProcess(selected, maskType, threshold);
    },
    [maskType, threshold, runProcess],
  );

  const handleToggleDetection = useCallback(
    (id: string) => {
      setExcludedIds((prev) => {
        const next = new Set(prev);
        if (next.has(id)) {
          next.delete(id);
        } else {
          next.add(id);
        }
        void runRemask({ maskType, threshold, excludedIds: next });
        return next;
      });
    },
    [maskType, threshold, runRemask],
  );

  const handleMaskChange = useCallback(
    (mask: MaskType) => {
      setMaskType(mask);
      if (result) void runRemask({ maskType: mask, threshold, excludedIds });
    },
    [result, threshold, excludedIds, runRemask],
  );

  const handleThresholdChange = useCallback(
    (value: number) => {
      setThreshold(value);
      if (!result) return;
      // Debounce slider drags so we don't flood the remask endpoint.
      if (sliderTimer.current !== null) window.clearTimeout(sliderTimer.current);
      sliderTimer.current = window.setTimeout(() => {
        void runRemask({ maskType, threshold: value, excludedIds });
      }, 350);
    },
    [result, maskType, excludedIds, runRemask],
  );

  const handleDownload = useCallback(async () => {
    if (!result) return;
    setDownloading(true);
    setError(null);
    try {
      // Uses the stored masked image — always matches the on-screen preview.
      const blob = await downloadJobImage(result.job_id);
      const base = file?.name.replace(/\.[^.]+$/, '') ?? result.job_id;
      saveBlob(blob, `redacted_${base}.png`);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setDownloading(false);
    }
  }, [result, file]);

  return (
    <div className="space-y-6">
      <div className="text-center animate-slide-up">
        <h2 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
          Review &amp; Redact
        </h2>
        <p className="text-gray-600 dark:text-gray-400 max-w-2xl mx-auto">
          Upload a document, inspect every detection, and uncheck anything you want
          to keep — the masked preview updates instantly without re-uploading.
        </p>
      </div>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      <div className="grid lg:grid-cols-2 gap-8">
        {/* Left column: upload + controls */}
        <div className="space-y-6">
          <div className="glass-panel p-6">
            <h3 className="text-lg font-semibold mb-4 text-gray-800 dark:text-white">
              Upload Document
            </h3>
            <DropZone onFileSelect={handleFileSelect} onReject={setError} />
            {localPreview && !result && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                className="mt-4 rounded-xl overflow-hidden border border-gray-200 dark:border-dark-700"
              >
                <img
                  src={localPreview}
                  alt="Upload preview"
                  className="w-full h-48 object-contain bg-gray-100 dark:bg-dark-900"
                />
                <p className="text-sm text-gray-500 p-2 text-center">{file?.name}</p>
              </motion.div>
            )}
            {processing && (
              <p className="mt-4 flex items-center justify-center gap-2 text-sm text-primary-600 dark:text-primary-400">
                <Loader className="w-4 h-4 animate-spin" />
                Detecting PII — this can take a moment…
              </p>
            )}
          </div>

          <div className="glass-panel p-6">
            <h3 className="text-lg font-semibold mb-4 text-gray-800 dark:text-white">
              Masking Style
            </h3>
            <MaskSelector selected={maskType} onChange={handleMaskChange} />

            <div className="mt-6">
              <div className="flex items-center justify-between mb-2">
                <label
                  htmlFor="confidence-slider"
                  className="text-sm font-medium text-gray-700 dark:text-gray-300"
                >
                  Confidence threshold
                </label>
                <span className="text-sm font-mono text-primary-600 dark:text-primary-400">
                  {(threshold * 100).toFixed(0)}%
                </span>
              </div>
              <input
                id="confidence-slider"
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={threshold}
                onChange={(e) => handleThresholdChange(Number(e.target.value))}
                className="w-full accent-primary-600"
              />
              <p className="text-xs text-gray-400 mt-1">
                Only detections at or above this confidence are masked.
              </p>
            </div>
          </div>

          {result && (
            <div className="flex gap-3">
              <button
                onClick={() => file && void runProcess(file, maskType, threshold)}
                disabled={processing || remasking}
                className="btn-secondary flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <RefreshCw className={`w-4 h-4 ${processing ? 'animate-spin' : ''}`} />
                Re-run detection
              </button>
              <button
                onClick={() => void handleDownload()}
                disabled={downloading || processing}
                className="btn-primary flex-1 flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {downloading ? (
                  <Loader className="w-5 h-5 animate-spin" />
                ) : (
                  <Download className="w-5 h-5" />
                )}
                {downloading ? 'Downloading…' : 'Download masked image'}
              </button>
            </div>
          )}
        </div>

        {/* Right column: previews + detections */}
        <div className="space-y-6">
          {result ? (
            <motion.div
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              className="space-y-6"
            >
              <div className="glass-panel p-6">
                <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
                  <h3 className="text-lg font-semibold text-gray-800 dark:text-white">
                    Before / After
                  </h3>
                  <div className="flex items-center gap-3">
                    <span className="px-3 py-1 bg-green-100 dark:bg-green-900/30 text-green-700 dark:text-green-400 rounded-full text-sm font-medium flex items-center gap-1">
                      <CheckCircle className="w-4 h-4" />
                      {result.pii_count} PII found
                    </span>
                    <span className="flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400">
                      <Clock className="w-4 h-4" />
                      {result.processing_time_ms.toFixed(0)}ms
                    </span>
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <figure>
                    <img
                      src={toDataUrl(result.original_image_base64)}
                      alt="Original document"
                      className="w-full rounded-lg border border-gray-200 dark:border-dark-700 bg-gray-100 dark:bg-dark-900 object-contain"
                    />
                    <figcaption className="text-xs text-center text-gray-500 mt-1">
                      Original
                    </figcaption>
                  </figure>
                  <figure className="relative">
                    <img
                      src={toDataUrl(result.masked_image_base64)}
                      alt="Masked document"
                      className={`w-full rounded-lg border border-gray-200 dark:border-dark-700 bg-gray-100 dark:bg-dark-900 object-contain transition-opacity ${
                        remasking ? 'opacity-40' : 'opacity-100'
                      }`}
                    />
                    <figcaption className="text-xs text-center text-gray-500 mt-1 flex items-center justify-center gap-1">
                      {remasking && <Loader className="w-3 h-3 animate-spin" />}
                      Masked
                    </figcaption>
                  </figure>
                </div>
              </div>

              <div className="glass-panel p-6">
                <div className="flex items-center justify-between mb-1">
                  <h3 className="text-lg font-semibold text-gray-800 dark:text-white">
                    Detections
                  </h3>
                  {excludedIds.size > 0 && (
                    <span className="text-xs text-amber-600 dark:text-amber-400">
                      {excludedIds.size} excluded from masking
                    </span>
                  )}
                </div>
                <p className="text-xs text-gray-400 mb-4">
                  Uncheck a detection to keep it visible in the output.
                </p>
                <DetectionList
                  detections={result.detections}
                  excludedIds={excludedIds}
                  onToggle={handleToggleDetection}
                  disabled={processing}
                />
              </div>
            </motion.div>
          ) : (
            !processing && (
              <div className="glass-panel p-10 text-center text-gray-400 dark:text-gray-600 h-full flex flex-col items-center justify-center">
                <Shield className="w-16 h-16 mx-auto mb-4 opacity-30" />
                <p>Upload a document to review detections</p>
              </div>
            )
          )}
        </div>
      </div>
    </div>
  );
};
