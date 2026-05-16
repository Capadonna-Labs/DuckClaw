'use client';

import { AlertTriangle } from 'lucide-react';

export interface DangerConfirmDetail {
  label: string;
  value: string;
}

interface ConfirmDangerModalProps {
  isOpen: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  details: DangerConfirmDetail[];
  isLoading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDangerModal({
  isOpen,
  title,
  description,
  confirmLabel = 'Sí, eliminar',
  details,
  isLoading = false,
  onConfirm,
  onCancel,
}: ConfirmDangerModalProps) {
  if (!isOpen) return null;

  return (
    <>
      <div className="fixed inset-0 bg-slate-900/70 backdrop-blur-sm z-[200]" aria-hidden />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="danger-modal-title"
        className="fixed top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 z-[201] w-full max-w-lg bg-white dark:bg-dark-surface rounded-2xl shadow-2xl overflow-hidden border border-red-200 dark:border-red-900"
      >
        <div className="bg-red-700 p-5 flex items-start gap-3">
          <AlertTriangle className="text-red-100 shrink-0" size={22} />
          <div>
            <h2 id="danger-modal-title" className="text-white font-bold text-lg">
              {title}
            </h2>
            <p className="text-red-100/90 text-sm mt-1">{description}</p>
          </div>
        </div>

        <div className="p-5 space-y-4">
          <dl className="rounded-xl border dark:border-dark-border overflow-hidden text-sm">
            {details.map((d, i) => (
              <div
                key={d.label}
                className={`flex gap-3 px-4 py-2.5 ${
                  i > 0 ? 'border-t dark:border-dark-border' : ''
                } bg-gov-gray-50 dark:bg-dark-bg`}
              >
                <dt className="text-gov-gray-500 w-28 shrink-0 font-medium">{d.label}</dt>
                <dd className="font-mono text-xs break-all">{d.value}</dd>
              </div>
            ))}
          </dl>
          <p className="text-xs text-gov-gray-500">
            Esta acción no se puede deshacer. Quedará registrada en auditoría.
          </p>
        </div>

        <div className="flex justify-end gap-3 p-4 border-t dark:border-dark-border bg-gov-gray-50 dark:bg-dark-bg">
          <button
            type="button"
            onClick={onCancel}
            disabled={isLoading}
            className="px-4 py-2 text-sm font-semibold rounded-xl border dark:border-dark-border"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isLoading}
            className="px-4 py-2 text-sm font-bold rounded-xl bg-red-600 text-white hover:bg-red-700 disabled:opacity-50"
          >
            {isLoading ? 'Procesando…' : confirmLabel}
          </button>
        </div>
      </div>
    </>
  );
}
