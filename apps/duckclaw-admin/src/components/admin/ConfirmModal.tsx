'use client';

import { useEffect } from 'react';
import { UserPlus } from 'lucide-react';

export type ConfirmDetail = {
  label: string;
  value: string;
};

type ConfirmModalProps = {
  isOpen: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  details: ConfirmDetail[];
  isLoading?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

/** Modal de confirmación (acción no destructiva). ESC / Cancel cancelan. */
export default function ConfirmModal({
  isOpen,
  title,
  description,
  confirmLabel = 'Confirmar',
  details,
  isLoading = false,
  onConfirm,
  onCancel,
}: ConfirmModalProps) {
  useEffect(() => {
    if (!isOpen) return undefined;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isLoading) onCancel();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, isLoading, onCancel]);

  if (!isOpen) return null;

  return (
    <>
      <div
        className="fixed inset-0 z-[200] bg-slate-900/70 backdrop-blur-sm"
        aria-hidden
        onClick={() => {
          if (!isLoading) onCancel();
        }}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-modal-title"
        className="fixed left-1/2 top-1/2 z-[201] w-full max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-2xl border border-gov-blue-200 bg-white shadow-2xl dark:border-gov-blue-900 dark:bg-dark-surface"
      >
        <div className="flex items-start gap-3 bg-gov-blue-700 p-5 dark:bg-gov-blue-900">
          <UserPlus className="shrink-0 text-gov-blue-100" size={22} aria-hidden />
          <div>
            <h2 id="confirm-modal-title" className="text-lg font-bold text-white">
              {title}
            </h2>
            <p className="mt-1 text-sm text-gov-blue-100/90">{description}</p>
          </div>
        </div>

        <div className="space-y-3 p-5">
          <dl className="overflow-hidden rounded-xl border text-sm dark:border-dark-border">
            {details.map((d, i) => (
              <div
                key={d.label}
                className={`flex gap-3 bg-gov-gray-50 px-4 py-2.5 dark:bg-dark-bg ${
                  i > 0 ? 'border-t dark:border-dark-border' : ''
                }`}
              >
                <dt className="w-28 shrink-0 font-medium text-gov-gray-500">{d.label}</dt>
                <dd className="break-all font-mono text-xs text-gov-gray-900 dark:text-dark-text">
                  {d.value}
                </dd>
              </div>
            ))}
          </dl>
          <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
            Sin grant, el agente no verá las tools MCP aunque el conector tenga auth OK.
          </p>
        </div>

        <div className="flex justify-end gap-3 border-t bg-gov-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
          <button
            type="button"
            onClick={onCancel}
            disabled={isLoading}
            className="rounded-xl border px-4 py-2 text-sm font-semibold dark:border-dark-border"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isLoading}
            className="rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-bold text-white hover:bg-gov-blue-800 disabled:opacity-50 dark:bg-dark-cyan dark:text-dark-bg"
          >
            {isLoading ? 'Aplicando…' : confirmLabel}
          </button>
        </div>
      </div>
    </>
  );
}
