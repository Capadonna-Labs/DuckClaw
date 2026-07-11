'use client';

import { X } from 'lucide-react';
import { KnowledgeFolderBrowser } from '@/components/knowledge/KnowledgeFolderBrowser';

type KnowledgeFolderPickerProps = {
  open: boolean;
  initialPath?: string;
  onClose: () => void;
  onSelect: (path: string) => void;
};

export function KnowledgeFolderPicker({
  open,
  initialPath = '',
  onClose,
  onSelect,
}: KnowledgeFolderPickerProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div
        role="dialog"
        aria-modal
        aria-labelledby="knowledge-folder-picker-title"
        className="flex max-h-[85vh] w-full max-w-xl flex-col overflow-hidden rounded-3xl border border-gov-gray-100 bg-white shadow-xl dark:border-dark-border dark:bg-dark-surface"
      >
        <div className="flex items-start justify-between gap-3 border-b border-gov-gray-100 px-5 py-4 dark:border-dark-border">
          <div className="min-w-0">
            <p id="knowledge-folder-picker-title" className="text-lg font-black dark:text-dark-text">
              Elegir carpeta
            </p>
            <p className="mt-1 text-xs text-gov-gray-500 dark:text-dark-muted">
              Carpetas bajo <code className="font-mono">DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS</code>.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 hover:bg-gov-gray-100 dark:hover:bg-dark-bg"
            aria-label="Cerrar"
          >
            <X size={18} />
          </button>
        </div>

        <KnowledgeFolderBrowser
          initialPath={initialPath}
          onSelect={(path) => {
            onSelect(path);
            onClose();
          }}
          className="mx-4 mb-4 mt-3 border-0 bg-transparent"
        />

        <div className="flex justify-end border-t border-gov-gray-100 px-5 py-4 dark:border-dark-border">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border px-4 py-2 text-sm font-semibold dark:border-dark-border"
          >
            Cancelar
          </button>
        </div>
      </div>
    </div>
  );
}
