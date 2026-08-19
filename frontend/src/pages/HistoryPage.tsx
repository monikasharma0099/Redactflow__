import { useState, useCallback, useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { Download, Trash2, RefreshCw, Loader, History } from 'lucide-react';
import axios from 'axios';
import { ErrorBanner } from '../components/ErrorBanner';
import {
  getHistory,
  deleteHistoryItem,
  downloadJobImage,
  getErrorMessage,
  saveBlob,
} from '../utils/api';
import type { HistoryItem } from '../types';

const formatDate = (iso: string): string => {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? iso : date.toLocaleString();
};

export const HistoryPage = () => {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const requestCtrl = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    requestCtrl.current?.abort();
    const ctrl = new AbortController();
    requestCtrl.current = ctrl;
    setLoading(true);
    setError(null);
    try {
      const history = await getHistory(ctrl.signal);
      setItems(history);
    } catch (err) {
      if (!axios.isCancel(err)) setError(getErrorMessage(err));
    } finally {
      if (requestCtrl.current === ctrl) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    return () => requestCtrl.current?.abort();
  }, [load]);

  const handleDownload = useCallback(async (item: HistoryItem) => {
    setBusyId(item.job_id);
    setError(null);
    try {
      const blob = await downloadJobImage(item.job_id);
      const base = item.filename.replace(/\.[^.]+$/, '') || item.job_id;
      saveBlob(blob, `redacted_${base}.png`);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusyId(null);
    }
  }, []);

  const handleDelete = useCallback(
    async (item: HistoryItem) => {
      setBusyId(item.job_id);
      setError(null);
      try {
        await deleteHistoryItem(item.job_id);
        setItems((prev) => prev.filter((i) => i.job_id !== item.job_id));
      } catch (err) {
        setError(getErrorMessage(err));
      } finally {
        setBusyId(null);
      }
    },
    [],
  );

  return (
    <div className="max-w-5xl mx-auto space-y-6">
      <div className="text-center animate-slide-up">
        <h2 className="text-3xl font-bold text-gray-900 dark:text-white mb-2">
          Job History
        </h2>
        <p className="text-gray-600 dark:text-gray-400">
          The 50 most recent redaction jobs. Re-download outputs or delete them
          (jobs also expire automatically after 7 days).
        </p>
      </div>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      <div className="glass-panel p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-gray-800 dark:text-white flex items-center gap-2">
            <History className="w-5 h-5" />
            Recent jobs
          </h3>
          <button
            onClick={() => void load()}
            disabled={loading}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-dark-700 transition-colors disabled:opacity-40"
            aria-label="Refresh history"
          >
            <RefreshCw className={`w-4 h-4 text-gray-600 dark:text-gray-300 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>

        {loading && items.length === 0 ? (
          <p className="text-center py-10 text-gray-400 flex items-center justify-center gap-2">
            <Loader className="w-4 h-4 animate-spin" />
            Loading history…
          </p>
        ) : items.length === 0 ? (
          <p className="text-center py-10 text-gray-400">
            No jobs yet — redact a document and it will appear here.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wide text-gray-400 border-b border-gray-200 dark:border-dark-600">
                  <th className="py-2 pr-4">Filename</th>
                  <th className="py-2 pr-4">Kind</th>
                  <th className="py-2 pr-4">PII</th>
                  <th className="py-2 pr-4">Mask</th>
                  <th className="py-2 pr-4">Created</th>
                  <th className="py-2 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((item, idx) => (
                  <motion.tr
                    key={item.job_id}
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: Math.min(idx * 0.02, 0.4) }}
                    className="border-b border-gray-100 dark:border-dark-700 last:border-0"
                  >
                    <td className="py-3 pr-4 max-w-[16rem]">
                      <span className="block truncate text-gray-700 dark:text-gray-300" title={item.filename}>
                        {item.filename}
                      </span>
                      <span className="block text-[11px] font-mono text-gray-400">
                        {item.job_id.slice(0, 8)}
                      </span>
                    </td>
                    <td className="py-3 pr-4">
                      <span className="px-2 py-0.5 rounded text-xs font-medium bg-gray-100 dark:bg-dark-700 text-gray-600 dark:text-gray-300">
                        {item.kind}
                      </span>
                    </td>
                    <td className="py-3 pr-4 text-gray-600 dark:text-gray-400">
                      {item.pii_count}
                    </td>
                    <td className="py-3 pr-4 text-gray-600 dark:text-gray-400">
                      {item.mask_type}
                    </td>
                    <td className="py-3 pr-4 text-gray-500 dark:text-gray-400 whitespace-nowrap">
                      {formatDate(item.created_at)}
                    </td>
                    <td className="py-3 text-right whitespace-nowrap">
                      <button
                        onClick={() => void handleDownload(item)}
                        disabled={busyId === item.job_id}
                        className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-dark-700 transition-colors disabled:opacity-40"
                        aria-label={`Download ${item.filename}`}
                        title="Download masked output"
                      >
                        {busyId === item.job_id ? (
                          <Loader className="w-4 h-4 animate-spin text-gray-500" />
                        ) : (
                          <Download className="w-4 h-4 text-primary-600 dark:text-primary-400" />
                        )}
                      </button>
                      <button
                        onClick={() => void handleDelete(item)}
                        disabled={busyId === item.job_id}
                        className="p-2 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors disabled:opacity-40"
                        aria-label={`Delete ${item.filename}`}
                        title="Delete job and artifacts"
                      >
                        <Trash2 className="w-4 h-4 text-red-500" />
                      </button>
                    </td>
                  </motion.tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
