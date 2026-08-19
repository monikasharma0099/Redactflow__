import { useCallback } from 'react';
import { useDropzone, type FileRejection } from 'react-dropzone';
import { Upload, FileImage, FileText } from 'lucide-react';

interface DropZoneProps {
  onFileSelect: (files: File[]) => void;
  /** Called with a user-facing message when files are rejected (wrong type, too many). */
  onReject?: (message: string) => void;
  accept?: 'image' | 'pdf';
  multiple?: boolean;
  maxFiles?: number;
}

const acceptMap = {
  image: { 'image/png': ['.png'], 'image/jpeg': ['.jpg', '.jpeg'] },
  pdf: { 'application/pdf': ['.pdf'] },
} as const;

export const DropZone = ({
  onFileSelect,
  onReject,
  accept = 'image',
  multiple = false,
  maxFiles,
}: DropZoneProps) => {
  const handleRejected = useCallback(
    (rejections: FileRejection[]) => {
      if (!onReject || rejections.length === 0) return;
      const tooMany = rejections.some((r) =>
        r.errors.some((e) => e.code === 'too-many-files'),
      );
      if (tooMany) {
        onReject(`Too many files — the maximum is ${maxFiles ?? 1}.`);
        return;
      }
      onReject(
        accept === 'pdf'
          ? 'Only PDF files (application/pdf) are accepted here.'
          : 'Only PNG or JPEG images are accepted here.',
      );
    },
    [accept, maxFiles, onReject],
  );

  const onDrop = useCallback(
    (acceptedFiles: File[]) => {
      if (acceptedFiles.length > 0) onFileSelect(acceptedFiles);
    },
    [onFileSelect],
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    onDropRejected: handleRejected,
    accept: acceptMap[accept],
    multiple,
    maxFiles: multiple ? maxFiles : 1,
  });

  const hint = accept === 'pdf' ? 'PDF only' : 'PNG, JPG';

  return (
    <div
      {...getRootProps()}
      className={`
        border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer
        transition-all duration-300
        ${isDragActive
          ? 'border-primary-500 bg-primary-50 dark:bg-primary-900/20'
          : 'border-gray-300 dark:border-dark-600 hover:border-primary-400 dark:hover:border-primary-500'
        }
      `}
    >
      <input {...getInputProps()} />
      <div className="flex flex-col items-center gap-4">
        <div className="p-4 bg-primary-100 dark:bg-primary-900/30 rounded-full">
          <Upload className="w-8 h-8 text-primary-600 dark:text-primary-400" />
        </div>
        <div>
          <p className="text-lg font-semibold text-gray-800 dark:text-gray-200">
            {isDragActive ? 'Drop files here' : 'Drag & drop files here'}
          </p>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            or click to browse • Supports {hint}
            {multiple && maxFiles ? ` • up to ${maxFiles} files` : ''}
          </p>
        </div>
        <div className="flex gap-3 mt-2">
          {accept === 'image' ? (
            <div className="flex items-center gap-1 text-xs text-gray-400">
              <FileImage className="w-4 h-4" />
              <span>Images</span>
            </div>
          ) : (
            <div className="flex items-center gap-1 text-xs text-gray-400">
              <FileText className="w-4 h-4" />
              <span>PDF</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
