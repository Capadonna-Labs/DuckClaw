'use client';

import { Upload } from 'lucide-react';
import { useCallback, useRef, useState, type DragEvent } from 'react';
import {
  titleFromHtmlFilename,
  validateHtmlUploadFile,
  validateHtmlUploadText,
} from '@/lib/htmlDashboardUpload';

type HtmlDashboardUploadZoneProps = {
  disabled?: boolean;
  onUpload: (file: File, title: string) => Promise<void>;
};

export function HtmlDashboardUploadZone({ disabled, onUpload }: HtmlDashboardUploadZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);
  const [error, setError] = useState('');
  const [uploading, setUploading] = useState(false);

  const handleFile = useCallback(
    async (file: File | undefined) => {
      if (!file || disabled || uploading) return;
      const fileErr = validateHtmlUploadFile(file);
      if (fileErr) {
        setError(fileErr);
        return;
      }
      setError('');
      setUploading(true);
      try {
        const text = await file.text();
        const textErr = validateHtmlUploadText(text);
        if (textErr) {
          setError(textErr);
          return;
        }
        await onUpload(file, titleFromHtmlFilename(file.name));
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Error al subir');
      } finally {
        setUploading(false);
      }
    },
    [disabled, onUpload, uploading]
  );

  const onDrop = useCallback(
    (e: DragEvent) => {
      e.preventDefault();
      setDragOver(false);
      void handleFile(e.dataTransfer.files?.[0]);
    },
    [handleFile]
  );

  return (
    <div className="pointer-events-auto absolute inset-0 z-30 flex items-center justify-center bg-white/85 p-6 backdrop-blur-[1px]">
      <div
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click();
        }}
        onDragEnter={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          setDragOver(false);
        }}
        onDrop={onDrop}
        onClick={() => inputRef.current?.click()}
        className={`flex max-w-md flex-col items-center gap-3 rounded-xl border-2 border-dashed px-8 py-10 text-center transition ${
          dragOver
            ? 'border-sky-500 bg-sky-50'
            : 'border-slate-300 bg-white hover:border-sky-400 hover:bg-slate-50'
        } ${disabled || uploading ? 'cursor-not-allowed opacity-60' : 'cursor-pointer'}`}
      >
        <Upload className="h-8 w-8 text-sky-600" aria-hidden />
        <div>
          <p className="text-sm font-medium text-slate-800">
            {uploading ? 'Publicando HTML…' : 'Subir dashboard .html'}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Arrastra un archivo o haz clic. Máx. 512 KB. Mismo flujo que{' '}
            <code className="text-slate-600">publish_custom_report</code>.
          </p>
        </div>
        <input
          ref={inputRef}
          type="file"
          accept=".html,.htm,text/html"
          className="hidden"
          disabled={disabled || uploading}
          onChange={(e) => void handleFile(e.target.files?.[0])}
        />
        {error ? <p className="text-xs text-red-600">{error}</p> : null}
      </div>
    </div>
  );
}
