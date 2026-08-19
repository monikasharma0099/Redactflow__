import { motion } from 'framer-motion';
import type { PIIDetection } from '../types';

interface DetectionListProps {
  detections: PIIDetection[];
  /** Ids the user has unchecked — these stay visible in the masked output. */
  excludedIds: ReadonlySet<string>;
  onToggle: (id: string) => void;
  disabled?: boolean;
}

const sourceStyles: Record<string, string> = {
  regex: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400',
  spacy: 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400',
  llm: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-400',
};

const getConfidenceColor = (conf: number) => {
  if (conf >= 0.9) return 'text-green-500';
  if (conf >= 0.7) return 'text-yellow-500';
  return 'text-red-500';
};

/**
 * Human-in-the-loop review list: one checkbox per detection.
 * Checked = will be masked; unchecked = excluded via the remask endpoint.
 */
export const DetectionList = ({
  detections,
  excludedIds,
  onToggle,
  disabled = false,
}: DetectionListProps) => {
  if (detections.length === 0) {
    return (
      <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-6">
        No PII detected in this document.
      </p>
    );
  }

  return (
    <div className="space-y-2 max-h-96 overflow-y-auto pr-2">
      {detections.map((det, idx) => {
        const excluded = excludedIds.has(det.id);
        const unlocatable = det.bounding_box === null;
        return (
          <motion.label
            key={det.id}
            initial={{ opacity: 0, y: 5 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: Math.min(idx * 0.03, 0.5) }}
            className={`flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors ${
              excluded
                ? 'bg-gray-50 dark:bg-dark-700/30 border-gray-200 dark:border-dark-600 opacity-70'
                : 'bg-white dark:bg-dark-700/50 border-gray-200 dark:border-dark-600'
            } ${disabled || unlocatable ? 'cursor-not-allowed' : ''}`}
          >
            <input
              type="checkbox"
              checked={!excluded}
              disabled={disabled || unlocatable}
              onChange={() => onToggle(det.id)}
              className="mt-1 w-4 h-4 rounded border-gray-300 text-primary-600 focus:ring-primary-500 disabled:opacity-40"
              aria-label={`Mask ${det.pii_type}`}
            />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wide bg-primary-100 dark:bg-primary-900/30 text-primary-700 dark:text-primary-400">
                  {det.pii_type}
                </span>
                <span
                  className={`px-2 py-0.5 rounded text-xs font-medium ${
                    sourceStyles[det.source] ??
                    'bg-gray-100 text-gray-600 dark:bg-dark-600 dark:text-gray-300'
                  }`}
                >
                  {det.source}
                </span>
                <span className={`text-xs font-bold ml-auto ${getConfidenceColor(det.confidence)}`}>
                  {(det.confidence * 100).toFixed(0)}%
                </span>
              </div>
              <p className="text-xs text-gray-600 dark:text-gray-300 mt-1.5 font-mono break-all">
                {det.masked_text || det.text}
              </p>
              {unlocatable && (
                <p className="text-[11px] text-gray-400 mt-1">
                  Position not found on the image — left unmasked.
                </p>
              )}
            </div>
          </motion.label>
        );
      })}
    </div>
  );
};
