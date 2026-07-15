'use client';

import { useCallback, useEffect, useState } from 'react';
import { ChevronRight, FileText, Folder, FolderOpen, Home, Loader2, X } from 'lucide-react';
import { adminService, type KnowledgeBrowseEntry, type KnowledgeBrowseResponse } from '@/services/adminService';
import { formatKnowledgeError } from '@/components/knowledge/knowledgeErrorMessage';

type VaultDocxPickerProps = {
  open: boolean;
  initialPath?: string;
  onClose: () => void;
  onSelect: (path: string) => void;
};

function pathTail(path: string): string {
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
  return parts[parts.length - 1] || path;
}

function VaultDocxBrowser({
  initialPath,
  onSelectFile,
}: {
  initialPath: string;
  onSelectFile: (path: string) => void;
}) {
  const [payload, setPayload] = useState<KnowledgeBrowseResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (path: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await adminService.browseKnowledgeFolders(path, { files: 'docx' });
      setPayload(data);
    } catch (e) {
      setPayload(null);
      setError(formatKnowledgeError(e instanceof Error ? e.message : 'No se pudo listar el vault'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(initialPath.trim());
  }, [initialPath, load]);

  const navigate = (path: string) => {
    void load(path);
  };

  const openEntry = (entry: KnowledgeBrowseEntry) => {
    if (!entry.exists || !entry.selectable) return;
    if (entry.kind === 'file') {
      onSelectFile(entry.path);
      return;
    }
    void load(entry.path);
  };

  const directories = (payload?.entries || []).filter((e) => e.kind !== 'file');
  const files = (payload?.entries || []).filter((e) => e.kind === 'file');

  return (
    <div className="overflow-hidden rounded-2xl border border-slate-700 bg-slate-950">
      <div className="border-b border-slate-800 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => navigate('')}
            className="inline-flex items-center gap-1 rounded-lg border border-slate-700 px-2 py-1 text-xs font-semibold text-slate-200"
          >
            <Home size={12} />
            Inicio
          </button>
          {payload?.parent_path != null && !payload.roots_mode ? (
            <button
              type="button"
              onClick={() => navigate(payload.parent_path ?? '')}
              className="rounded-lg border border-slate-700 px-2 py-1 text-xs font-semibold text-slate-200"
            >
              Subir
            </button>
          ) : null}
        </div>
        <p className="mt-2 truncate font-mono text-[11px] text-slate-500">
          {payload?.roots_mode ? 'Elige una raíz permitida' : payload?.path || '—'}
        </p>
      </div>

      <div className="scrollbar-thin max-h-[360px] min-h-[220px] overflow-y-auto px-2 py-2">
        {loading ? (
          <p className="flex items-center gap-2 px-2 py-6 text-sm text-slate-500">
            <Loader2 size={16} className="animate-spin" />
            Cargando…
          </p>
        ) : null}
        {error ? (
          <p role="alert" className="mx-2 my-3 rounded-xl border border-red-900/60 bg-red-950/40 px-3 py-2 text-sm text-red-300">
            {error}
          </p>
        ) : null}
        {!loading && !error && payload ? (
          directories.length === 0 && files.length === 0 ? (
            <p className="px-2 py-6 text-sm text-slate-500">
              No hay carpetas ni .docx aquí. Sube o elige otra carpeta.
            </p>
          ) : (
            <div className="space-y-3">
              {directories.length > 0 ? (
                <ul className="space-y-1">
                  {directories.map((entry) => (
                    <li key={entry.path}>
                      <button
                        type="button"
                        disabled={!entry.exists || !entry.selectable}
                        onClick={() => openEntry(entry)}
                        className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm text-slate-200 hover:bg-slate-900 disabled:opacity-40"
                      >
                        {entry.kind === 'root' ? (
                          <FolderOpen size={16} className="shrink-0 text-sky-400" />
                        ) : (
                          <Folder size={16} className="shrink-0 text-sky-500" />
                        )}
                        <span className="min-w-0 flex-1 truncate font-medium">{entry.name}</span>
                        <ChevronRight size={14} className="shrink-0 text-slate-600" />
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
              {files.length > 0 ? (
                <div>
                  <p className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                    Archivos .docx
                  </p>
                  <ul className="space-y-1">
                    {files.map((entry) => (
                      <li key={entry.path}>
                        <button
                          type="button"
                          disabled={!entry.exists || !entry.selectable}
                          onClick={() => openEntry(entry)}
                          className="flex w-full items-center gap-2 rounded-lg border border-slate-800 bg-slate-900/60 px-2 py-2 text-left text-sm text-slate-100 hover:border-sky-600 hover:bg-sky-950/30 disabled:opacity-40"
                        >
                          <FileText size={16} className="shrink-0 text-emerald-400" />
                          <span className="min-w-0 flex-1 truncate font-medium">{entry.name}</span>
                          <span className="shrink-0 text-[10px] font-semibold text-sky-400">Elegir</span>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : payload.roots_mode ? null : (
                <p className="px-2 text-xs text-slate-500">
                  Sin .docx en «{pathTail(payload.path)}». Entra a otra subcarpeta.
                </p>
              )}
            </div>
          )
        ) : null}
      </div>
    </div>
  );
}

export function VaultDocxPicker({
  open,
  initialPath = '',
  onClose,
  onSelect,
}: VaultDocxPickerProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[220] flex items-center justify-center bg-black/60 p-4">
      <div
        role="dialog"
        aria-modal
        aria-labelledby="vault-docx-picker-title"
        className="flex max-h-[90vh] w-full max-w-xl flex-col overflow-hidden rounded-2xl border border-slate-700 bg-slate-900 shadow-2xl"
      >
        <div className="flex items-start justify-between gap-3 border-b border-slate-800 px-5 py-4">
          <div className="min-w-0">
            <p id="vault-docx-picker-title" className="text-lg font-semibold text-slate-100">
              Elegir plantilla .docx
            </p>
            <p className="mt-1 text-xs text-slate-500">
              Navega el vault permitido y selecciona el archivo Word (no hace falta pegar la ruta).
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg p-1 text-slate-400 hover:bg-slate-800 hover:text-slate-100"
            aria-label="Cerrar"
          >
            <X size={18} />
          </button>
        </div>

        <div className="px-4 py-3">
          <VaultDocxBrowser
            initialPath={initialPath}
            onSelectFile={(path) => {
              onSelect(path);
              onClose();
            }}
          />
        </div>

        <div className="flex justify-end border-t border-slate-800 px-5 py-4">
          <button
            type="button"
            onClick={onClose}
            className="rounded-xl border border-slate-700 px-4 py-2 text-sm font-semibold text-slate-300"
          >
            Cancelar
          </button>
        </div>
      </div>
    </div>
  );
}
