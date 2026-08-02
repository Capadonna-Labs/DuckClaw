'use client';

import { useCallback, useEffect, useState } from 'react';
import { ChevronRight, Folder, FolderOpen, Home, Loader2 } from 'lucide-react';
import { adminService, type KnowledgeBrowseEntry, type KnowledgeBrowseResponse } from '@/services/adminService';
import { formatKnowledgeError } from '@/components/knowledge/knowledgeErrorMessage';

type KnowledgeFolderBrowserProps = {
  selectedPath?: string;
  initialPath?: string;
  onSelect: (path: string) => void;
  className?: string;
};

function pathLabel(path: string, rootsMode: boolean): string {
  if (rootsMode || !path.trim()) return 'Raíces permitidas';
  const parts = path.replace(/\\/g, '/').split('/').filter(Boolean);
  return parts[parts.length - 1] || path;
}

export function KnowledgeFolderBrowser({
  selectedPath = '',
  initialPath = '',
  onSelect,
  className = '',
}: KnowledgeFolderBrowserProps) {
  const [payload, setPayload] = useState<KnowledgeBrowseResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (path: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await adminService.browseKnowledgeFolders(path);
      setPayload(data);
    } catch (e) {
      setPayload(null);
      setError(formatKnowledgeError(e instanceof Error ? e.message : 'No se pudo listar carpetas'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(initialPath.trim());
  }, [initialPath, load]);

  const currentPath = payload?.path ?? '';
  const canSelectCurrent =
    Boolean(currentPath) && !loading && !error && payload?.path && !payload.roots_mode;

  const navigate = (path: string) => {
    void load(path);
  };

  const openEntry = (entry: KnowledgeBrowseEntry) => {
    if (!entry.exists || !entry.selectable) return;
    if (entry.kind === 'file') return;
    void load(entry.path);
  };

  return (
    <div
      className={`overflow-hidden rounded-2xl border border-gov-blue-100 bg-gov-gray-50/50 dark:border-dark-border dark:bg-dark-bg ${className}`}
    >
      <div className="border-b border-gov-blue-100 px-4 py-3 dark:border-dark-border">
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => navigate('')}
            className="inline-flex items-center gap-1 rounded-lg border border-gov-blue-200 px-2 py-1 text-xs font-bold dark:border-dark-border"
          >
            <Home size={12} />
            Inicio
          </button>
          {payload?.parent_path != null && payload.parent_path !== undefined && !payload.roots_mode ? (
            <button
              type="button"
              onClick={() => navigate(payload.parent_path ?? '')}
              className="rounded-lg border border-gov-blue-200 px-2 py-1 text-xs font-bold dark:border-dark-border"
            >
              Subir
            </button>
          ) : null}
          {canSelectCurrent ? (
            <button
              type="button"
              onClick={() => onSelect(currentPath)}
              className="ml-auto rounded-lg bg-gov-blue-700 px-3 py-1 text-xs font-black text-white"
            >
              Elegir {pathLabel(currentPath, payload?.roots_mode ?? true)}
            </button>
          ) : null}
        </div>
        <p className="mt-2 truncate font-mono text-[11px] text-gov-gray-600 dark:text-dark-muted">
          {selectedPath.trim() ? (
            <>
              <span className="font-bold text-gov-blue-800 dark:text-dark-cyan">Seleccionada: </span>
              {selectedPath}
            </>
          ) : payload?.roots_mode ? (
            'Carpetas en disco (permitidas). Elegir no las pone en el chat.'
          ) : (
            currentPath || '—'
          )}
        </p>
      </div>

      <div className="scrollbar-thin max-h-[280px] min-h-[200px] overflow-y-auto px-2 py-2">
        {loading ? (
          <p className="flex items-center gap-2 px-2 py-6 text-sm text-gov-gray-500 dark:text-dark-muted">
            <Loader2 size={16} className="animate-spin" />
            Cargando carpetas…
          </p>
        ) : null}
        {error ? (
          <p
            role="alert"
            className="mx-2 my-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300"
          >
            {error}
          </p>
        ) : null}
        {!loading && !error && payload ? (
          payload.entries.filter((e) => e.kind !== 'file').length === 0 ? (
            <p className="px-2 py-6 text-sm text-gov-gray-500 dark:text-dark-muted">
              No hay subcarpetas aquí. Usa «Elegir …» arriba si esta carpeta contiene documentos.
            </p>
          ) : (
            <ul className="space-y-1">
              {payload.entries
                .filter((e) => e.kind !== 'file')
                .map((entry) => (
                <li key={entry.path}>
                  <div className="flex items-center gap-1 rounded-xl px-1 py-1 hover:bg-white/80 dark:hover:bg-dark-surface">
                    <button
                      type="button"
                      disabled={!entry.exists || !entry.selectable}
                      onClick={() => openEntry(entry)}
                      className="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-2 py-2 text-left text-sm disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {entry.kind === 'root' ? (
                        <FolderOpen size={16} className="shrink-0 text-gov-blue-700 dark:text-dark-cyan" />
                      ) : (
                        <Folder size={16} className="shrink-0 text-gov-blue-600 dark:text-dark-cyan" />
                      )}
                      <span className="min-w-0 flex-1 truncate font-semibold">{entry.name}</span>
                      {!entry.exists ? (
                        <span className="text-[10px] font-bold uppercase text-amber-700">No existe</span>
                      ) : (
                        <ChevronRight size={14} className="shrink-0 text-gov-gray-400" />
                      )}
                    </button>
                    {entry.exists && entry.selectable && entry.kind !== 'file' ? (
                      <button
                        type="button"
                        onClick={() => onSelect(entry.path)}
                        className="shrink-0 rounded-lg border border-gov-blue-200 px-2 py-1 text-[10px] font-black text-gov-blue-800 dark:border-dark-border dark:text-dark-cyan"
                      >
                        Elegir
                      </button>
                    ) : null}
                  </div>
                  {!payload.roots_mode ? (
                    <p className="truncate px-3 pb-1 font-mono text-[10px] text-gov-gray-400">{entry.path}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          )
        ) : null}
      </div>
    </div>
  );
}
