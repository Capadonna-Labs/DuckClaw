'use client';

import { useCallback, useRef, useState } from 'react';
import { Upload, X } from 'lucide-react';
import { adminService, type SpawnPackagePreview } from '@/services/adminService';

export type SpawnPackageAttachResult = {
  file: File;
  preview: SpawnPackagePreview;
  confirmHighRisk: boolean;
};

type Props = {
  open: boolean;
  onClose: () => void;
  /** Persist immediately (Agentes catalog). Ignored when previewOnly. */
  onImported?: () => void;
  /** Wizard mode: return preview attachment without importing. */
  previewOnly?: boolean;
  onPreviewAttached?: (result: SpawnPackageAttachResult) => void;
};

export function ImportSpawnPackageDialog({
  open,
  onClose,
  onImported,
  previewOnly = false,
  onPreviewAttached,
}: Props) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<SpawnPackagePreview | null>(null);
  const [confirmHighRisk, setConfirmHighRisk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reset = useCallback(() => {
    setFile(null);
    setPreview(null);
    setConfirmHighRisk(false);
    setError(null);
    if (inputRef.current) inputRef.current.value = '';
  }, []);

  const close = useCallback(() => {
    reset();
    onClose();
  }, [onClose, reset]);

  const runPreview = useCallback(async (selected: File) => {
    setBusy(true);
    setError(null);
    setPreview(null);
    setConfirmHighRisk(false);
    try {
      const result = await adminService.previewSpawnPackage(selected);
      setPreview(result.preview);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Preview falló');
    } finally {
      setBusy(false);
    }
  }, []);

  const onFileChange = useCallback(
    (f: File | null) => {
      setFile(f);
      if (f) void runPreview(f);
    },
    [runPreview]
  );

  const importPackage = useCallback(async () => {
    if (!file || !preview) return;
    if (previewOnly) {
      onPreviewAttached?.({ file, preview, confirmHighRisk });
      close();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await adminService.importSpawnPackage(file, {
        confirm_high_risk: confirmHighRisk,
      });
      onImported?.();
      close();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import falló');
    } finally {
      setBusy(false);
    }
  }, [close, confirmHighRisk, file, onImported, onPreviewAttached, preview, previewOnly]);

  if (!open) return null;

  const highRisk = preview?.high_risk_findings ?? [];
  const needsConfirm = Boolean(preview?.import_blocked_until_confirm);
  const primaryLabel = previewOnly
    ? busy
      ? 'Adjuntando…'
      : 'Adjuntar al borrador'
    : busy
      ? 'Importando…'
      : 'Importar';

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-6 shadow-xl dark:bg-dark-surface">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-bold text-gov-gray-900 dark:text-dark-text">
              {previewOnly ? 'Adjuntar worker desde .zip' : 'Importar worker desde paquete'}
            </h2>
            <p className="mt-1 text-sm text-gov-gray-600 dark:text-dark-muted">
              {previewOnly
                ? 'Solo se hace preview ahora. El worker se crea al confirmar el proyecto.'
                : 'Sube un .zip de spawn exportado desde otra instancia DuckClaw.'}
            </p>
          </div>
          <button type="button" onClick={close} className="rounded-lg p-1 hover:bg-gov-gray-100 dark:hover:bg-dark-bg">
            <X size={18} />
          </button>
        </div>

        <input
          ref={inputRef}
          type="file"
          accept=".zip,.tar.gz,.tgz,application/zip,application/gzip"
          className="hidden"
          onChange={(e) => onFileChange(e.target.files?.[0] ?? null)}
        />
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          disabled={busy}
          className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-dashed px-4 py-6 text-sm dark:border-dark-border"
        >
          <Upload size={18} />
          {file ? file.name : 'Elegir paquete .zip'}
        </button>

        {preview ? (
          <div className="mt-4 space-y-3 text-sm">
            <p>
              <span className="font-semibold">Worker:</span> {preview.worker_id}
            </p>
            {preview.missing_tools.length > 0 ? (
              <div className="rounded-lg bg-amber-50 p-3 text-amber-900 dark:bg-amber-950/30 dark:text-amber-100">
                <p className="font-semibold">Tools opcionales ausentes</p>
                <p className="mt-1 break-all">{preview.missing_tools.join(', ')}</p>
              </div>
            ) : null}
            {highRisk.length > 0 ? (
              <div className="rounded-lg bg-red-50 p-3 text-red-900 dark:bg-red-950/30 dark:text-red-100">
                <p className="font-semibold">Tools de alto riesgo detectadas</p>
                <ul className="mt-2 list-disc pl-5">
                  {highRisk.map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
                <label className="mt-3 flex items-start gap-2">
                  <input
                    type="checkbox"
                    checked={confirmHighRisk}
                    onChange={(e) => setConfirmHighRisk(e.target.checked)}
                    className="mt-1"
                  />
                  <span>
                    Entiendo que este worker solicita capacidades sensibles. Acepto importarlo en modo
                    read-only sin exposición automática de mutaciones privilegiadas.
                  </span>
                </label>
              </div>
            ) : null}
          </div>
        ) : null}

        {error ? (
          <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300">
            {error}
          </p>
        ) : null}

        <div className="mt-6 flex justify-end gap-2">
          <button type="button" onClick={close} className="rounded-xl border px-4 py-2 text-sm dark:border-dark-border">
            Cancelar
          </button>
          <button
            type="button"
            disabled={!file || !preview || busy || (needsConfirm && !confirmHighRisk)}
            onClick={() => void importPackage()}
            className="rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            {primaryLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
