'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  ChevronRight,
  FileText,
  Folder,
  FolderOpen,
  Home,
  Loader2,
  Plus,
} from 'lucide-react';
import {
  adminService,
  type KnowledgeBrowseEntry,
  type KnowledgeBrowseResponse,
} from '@/services/adminService';
import { formatKnowledgeError } from '@/components/knowledge/knowledgeErrorMessage';

type ProductivityVaultBrowserProps = {
  onIndexed?: () => void;
};

export function ProductivityVaultBrowser({ onIndexed }: ProductivityVaultBrowserProps) {
  const [payload, setPayload] = useState<KnowledgeBrowseResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState('');
  const [busyPath, setBusyPath] = useState('');

  const load = useCallback(async (path: string) => {
    setLoading(true);
    setError(null);
    try {
      const data = await adminService.browseProductivityVault(path, '*');
      setPayload(data);
    } catch (e) {
      setPayload(null);
      setError(formatKnowledgeError(e instanceof Error ? e.message : 'No se pudo listar el vault'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load('');
  }, [load]);

  const openEntry = (entry: KnowledgeBrowseEntry) => {
    if (!entry.exists || !entry.selectable) return;
    if (entry.kind === 'file') return;
    void load(entry.path);
  };

  async function indexFile(entry: KnowledgeBrowseEntry) {
    setBusyPath(entry.path);
    setNotice('');
    setError(null);
    try {
      const res = await adminService.indexProductivityVaultPath({
        path: entry.path,
        title: entry.name,
      });
      setNotice(`Indexado en Artefactos: ${res.title || entry.name}`);
      onIndexed?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo indexar');
    } finally {
      setBusyPath('');
    }
  }

  const directories = (payload?.entries || []).filter((e) => e.kind !== 'file');
  const files = (payload?.entries || []).filter((e) => e.kind === 'file');

  return (
    <div className="overflow-hidden rounded-2xl border border-gov-blue-100 dark:border-dark-border">
      <div className="border-b border-gov-blue-100 px-4 py-3 dark:border-dark-border">
        <p className="text-sm font-black dark:text-dark-text">Vault OUTPUT</p>
        <p className="mt-1 text-xs text-gov-gray-500 dark:text-dark-muted">
          Carpetas bajo DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS. Indexa un archivo para verlo en la
          bandeja de Artefactos.
        </p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void load('')}
            className="inline-flex items-center gap-1 rounded-lg border border-gov-blue-200 px-2 py-1 text-xs font-bold dark:border-dark-border"
          >
            <Home size={12} />
            Inicio
          </button>
          {payload?.parent_path != null && !payload.roots_mode ? (
            <button
              type="button"
              onClick={() => void load(payload.parent_path ?? '')}
              className="rounded-lg border border-gov-blue-200 px-2 py-1 text-xs font-bold dark:border-dark-border"
            >
              Subir
            </button>
          ) : null}
        </div>
        <p className="mt-2 truncate font-mono text-[11px] text-gov-gray-500 dark:text-dark-muted">
          {payload?.roots_mode ? 'Raíces de salida' : payload?.path || '—'}
        </p>
      </div>

      <div className="scrollbar-thin max-h-[420px] min-h-[220px] overflow-y-auto px-2 py-2">
        {loading ? (
          <p className="flex items-center gap-2 px-2 py-6 text-sm text-gov-gray-500">
            <Loader2 size={16} className="animate-spin" />
            Cargando…
          </p>
        ) : null}
        {error ? (
          <p role="alert" className="mx-2 my-3 rounded-xl border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
            {error}
          </p>
        ) : null}
        {notice ? (
          <p className="mx-2 my-2 text-xs text-emerald-700 dark:text-emerald-300">{notice}</p>
        ) : null}
        {!loading && !error && payload ? (
          directories.length === 0 && files.length === 0 ? (
            <p className="px-2 py-6 text-sm text-gov-gray-500">Carpeta vacía.</p>
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
                        className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm hover:bg-gov-gray-50 disabled:opacity-40 dark:hover:bg-dark-bg"
                      >
                        {entry.kind === 'root' ? (
                          <FolderOpen size={16} className="shrink-0 text-emerald-600" />
                        ) : (
                          <Folder size={16} className="shrink-0 text-emerald-600" />
                        )}
                        <span className="min-w-0 flex-1 truncate font-semibold dark:text-dark-text">
                          {entry.name}
                        </span>
                        <ChevronRight size={14} className="text-gov-gray-400" />
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
              {files.length > 0 ? (
                <div>
                  <p className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wide text-gov-gray-500">
                    Archivos
                  </p>
                  <ul className="space-y-1">
                    {files.map((entry) => (
                      <li
                        key={entry.path}
                        className="flex items-center gap-2 rounded-lg border border-gov-gray-100 px-2 py-2 dark:border-dark-border"
                      >
                        <FileText size={16} className="shrink-0 text-gov-blue-700" />
                        <span className="min-w-0 flex-1 truncate text-sm font-medium dark:text-dark-text">
                          {entry.name}
                        </span>
                        <button
                          type="button"
                          disabled={busyPath === entry.path}
                          onClick={() => void indexFile(entry)}
                          className="inline-flex items-center gap-1 rounded-lg bg-gov-blue-700 px-2 py-1 text-[10px] font-black text-white disabled:opacity-50"
                        >
                          <Plus size={12} />
                          {busyPath === entry.path ? '…' : 'Indexar'}
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          )
        ) : null}
      </div>
    </div>
  );
}
