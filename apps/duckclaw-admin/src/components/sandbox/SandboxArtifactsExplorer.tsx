'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Braces,
  CloudUpload,
  Download,
  File,
  FileImage,
  FileText,
  Loader2,
  RefreshCw,
  Table2,
  Trash2,
} from 'lucide-react';
import {
  adminService,
  type SandboxArtifactMeta,
  type SandboxArtifactPreviewPayload,
  type SandboxRunSummary,
} from '@/services/adminService';
import { ChatMarkdown } from '@/components/chat/ChatMarkdown';

export type SandboxArtifactsExplorerProps = {
  /** Vacío = vista global (todos los chats). */
  chatId?: string;
  refreshKey?: number;
  highlightRunId?: string;
  tenantId?: string;
  projectId?: string;
};

type PreviewState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'image'; url: string; mime: string }
  | { status: 'json'; payload: SandboxArtifactPreviewPayload }
  | { status: 'error'; message: string };

function formatUnixTime(ts?: number): string {
  if (ts == null || !Number.isFinite(ts)) return '—';
  try {
    return new Date(ts * 1000).toLocaleString('es', {
      day: '2-digit',
      month: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    });
  } catch {
    return '—';
  }
}

function formatBytes(size?: number): string {
  if (size == null || !Number.isFinite(size) || size < 0) return '—';
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

function artifactIcon(mime: string, filename: string) {
  const mt = (mime || '').toLowerCase();
  const ext = filename.includes('.') ? filename.split('.').pop()?.toLowerCase() : '';
  if (mt.startsWith('image/')) return <FileImage size={14} className="shrink-0 text-sky-400" />;
  if (mt.includes('json') || ext === 'json') {
    return <Braces size={14} className="shrink-0 text-amber-400" />;
  }
  if (mt.includes('csv') || ext === 'csv') {
    return <Table2 size={14} className="shrink-0 text-emerald-400" />;
  }
  if (mt.startsWith('text/') || ext === 'md' || ext === 'markdown' || ext === 'txt') {
    return <FileText size={14} className="shrink-0 text-gov-blue-300" />;
  }
  return <File size={14} className="shrink-0 text-slate-400" />;
}

function exitCodeBadge(exitCode?: number): string {
  if (exitCode == null) return 'bg-slate-700 text-slate-300';
  if (exitCode === 0) return 'bg-emerald-900/50 text-emerald-200';
  return 'bg-red-900/50 text-red-200';
}

function TabularPreview({ payload }: { payload: SandboxArtifactPreviewPayload }) {
  const columns = payload.columns ?? [];
  const rows = (payload.rows ?? []) as unknown[][];
  if (!columns.length && !rows.length) {
    return <p className="text-xs text-slate-500">Sin filas para mostrar.</p>;
  }
  const headers = columns.length ? columns : (rows[0] as string[] | undefined) ?? [];
  const bodyRows = columns.length ? rows : rows.slice(1);
  return (
    <div className="max-h-64 overflow-auto rounded-lg border border-slate-800">
      <table className="min-w-full text-[10px] text-slate-200">
        {headers.length > 0 ? (
          <thead className="sticky top-0 bg-slate-900">
            <tr>
              {headers.map((col) => (
                <th key={String(col)} className="px-2 py-1 text-left font-semibold text-slate-400">
                  {String(col)}
                </th>
              ))}
            </tr>
          </thead>
        ) : null}
        <tbody>
          {bodyRows.map((row, idx) => (
            <tr key={idx} className="border-t border-slate-800/80 even:bg-slate-900/40">
              {(Array.isArray(row) ? row : [row]).map((cell, cellIdx) => (
                <td key={cellIdx} className="px-2 py-1 whitespace-nowrap">
                  {String(cell ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function JsonPreviewBody({ payload }: { payload: SandboxArtifactPreviewPayload }) {
  const text = payload.content ?? '';
  return (
    <pre className="max-h-64 overflow-auto rounded-lg border border-slate-800 bg-slate-950 p-2 text-[10px] font-mono text-slate-200 whitespace-pre-wrap">
      {text}
    </pre>
  );
}

function PreviewPane({
  artifact,
  chatId,
  preview,
  busy,
  onDelete,
  onSaveToVault,
}: {
  artifact: SandboxArtifactMeta | null;
  chatId: string;
  preview: PreviewState;
  busy: boolean;
  onDelete: () => void;
  onSaveToVault: () => void;
}) {
  if (!artifact) {
    return (
      <p className="flex flex-1 items-center justify-center p-4 text-xs text-slate-500">
        Selecciona un artefacto para previsualizar.
      </p>
    );
  }

  const downloadUrl = adminService.sandboxArtifactDownloadUrl(artifact.artifact_id, chatId);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <header className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-slate-800 px-3 py-2">
        <div className="min-w-0">
          <p className="truncate text-xs font-semibold text-slate-100" title={artifact.filename}>
            {artifact.filename}
          </p>
          <p className="text-[10px] text-slate-500">
            {artifact.mime || '—'} · {formatBytes(artifact.byte_size)}
          </p>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-1">
          <a
            href={downloadUrl}
            download={artifact.filename}
            className="inline-flex items-center gap-1 rounded-md bg-sky-600 px-2 py-1 text-[10px] font-semibold text-white hover:bg-sky-500"
          >
            <Download size={12} aria-hidden />
            Descargar
          </a>
          <button
            type="button"
            disabled={busy}
            onClick={onSaveToVault}
            className="inline-flex items-center gap-1 rounded-md border border-emerald-700 bg-emerald-950/50 px-2 py-1 text-[10px] font-semibold text-emerald-200 hover:bg-emerald-900/50 disabled:opacity-50"
          >
            <CloudUpload size={12} aria-hidden />
            Guardar en Drive
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={onDelete}
            className="inline-flex items-center gap-1 rounded-md border border-red-800 bg-red-950/40 px-2 py-1 text-[10px] font-semibold text-red-200 hover:bg-red-900/40 disabled:opacity-50"
          >
            <Trash2 size={12} aria-hidden />
            Eliminar
          </button>
        </div>
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {preview.status === 'loading' ? (
          <p className="flex items-center gap-2 text-xs text-slate-500">
            <Loader2 size={14} className="animate-spin" />
            Cargando vista previa…
          </p>
        ) : null}
        {preview.status === 'error' ? (
          <p className="text-xs text-amber-300">{preview.message}</p>
        ) : null}
        {preview.status === 'image' ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={preview.url}
            alt={artifact.filename}
            className="max-h-72 w-full rounded-lg border border-slate-800 object-contain bg-slate-950"
          />
        ) : null}
        {preview.status === 'json' ? (
          <div className="space-y-2">
            {preview.payload.preview_kind === 'markdown' ? (
              <div className="rounded-lg border border-slate-800 bg-slate-950 p-2">
                <ChatMarkdown content={preview.payload.content ?? ''} className="text-xs prose-sm" />
              </div>
            ) : preview.payload.preview_kind === 'tabular' ||
              preview.payload.preview_kind === 'parquet' ||
              preview.payload.preview_kind === 'csv' ? (
              <TabularPreview payload={preview.payload} />
            ) : (
              <JsonPreviewBody payload={preview.payload} />
            )}
          </div>
        ) : null}
        {preview.status === 'idle' && !artifact.previewable ? (
          <p className="text-xs text-slate-500">Sin vista previa para este tipo. Usa Descargar.</p>
        ) : null}
      </div>
    </div>
  );
}

export function SandboxArtifactsExplorer({
  chatId = '',
  refreshKey = 0,
  highlightRunId = '',
  tenantId,
  projectId,
}: SandboxArtifactsExplorerProps) {
  const [runs, setRuns] = useState<SandboxRunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedRunId, setSelectedRunId] = useState('');
  const [selectedRunChatId, setSelectedRunChatId] = useState('');
  const [artifacts, setArtifacts] = useState<SandboxArtifactMeta[]>([]);
  const [artifactsLoading, setArtifactsLoading] = useState(false);
  const [selectedArtifactId, setSelectedArtifactId] = useState('');
  const [preview, setPreview] = useState<PreviewState>({ status: 'idle' });
  const [busy, setBusy] = useState(false);
  const [chatFilter, setChatFilter] = useState(chatId.trim());

  const globalMode = !chatId.trim();

  const selectedArtifact = useMemo(
    () => artifacts.find((a) => a.artifact_id === selectedArtifactId) ?? null,
    [artifacts, selectedArtifactId]
  );

  const effectiveChatId = selectedRunChatId || chatFilter || chatId;

  const loadRuns = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const filter = (chatFilter || chatId).trim();
      const res = filter
        ? await adminService.listSandboxRuns(filter, 50)
        : await adminService.listAllSandboxRuns(50);
      const nextRuns = res.runs ?? [];
      setRuns(nextRuns);
      setSelectedRunId((prev) => {
        if (highlightRunId && nextRuns.some((r) => r.run_id === highlightRunId)) {
          const hit = nextRuns.find((r) => r.run_id === highlightRunId);
          if (hit?.chat_id) setSelectedRunChatId(String(hit.chat_id));
          return highlightRunId;
        }
        if (prev && nextRuns.some((r) => r.run_id === prev)) return prev;
        const first = nextRuns[0];
        if (first) {
          setSelectedRunChatId(String(first.chat_id || filter || ''));
          return first.run_id;
        }
        return '';
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudieron cargar las ejecuciones');
      setRuns([]);
      setSelectedRunId('');
    } finally {
      setLoading(false);
    }
  }, [chatId, chatFilter, highlightRunId]);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns, refreshKey]);

  useEffect(() => {
    if (!selectedRunId || !effectiveChatId.trim()) {
      setArtifacts([]);
      setSelectedArtifactId('');
      return;
    }
    let cancelled = false;
    setArtifactsLoading(true);
    adminService
      .getSandboxRun(selectedRunId, effectiveChatId.trim())
      .then((detail) => {
        if (cancelled) return;
        const list = detail.artifacts ?? [];
        setArtifacts(list);
        setSelectedArtifactId((prev) => {
          if (prev && list.some((a) => a.artifact_id === prev)) return prev;
          return list[0]?.artifact_id ?? '';
        });
      })
      .catch(() => {
        if (!cancelled) {
          setArtifacts([]);
          setSelectedArtifactId('');
        }
      })
      .finally(() => {
        if (!cancelled) setArtifactsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedRunId, effectiveChatId, refreshKey]);

  useEffect(() => {
    if (!selectedArtifact || !effectiveChatId.trim()) {
      setPreview({ status: 'idle' });
      return;
    }
    if (!selectedArtifact.previewable) {
      setPreview({ status: 'idle' });
      return;
    }

    let cancelled = false;
    const previewUrl = adminService.sandboxArtifactPreviewUrl(
      selectedArtifact.artifact_id,
      effectiveChatId.trim()
    );

    setPreview({ status: 'loading' });
    void fetch(previewUrl, { credentials: 'include', cache: 'no-store' })
      .then(async (res) => {
        if (cancelled) return;
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          const detail = typeof data?.detail === 'string' ? data.detail : `Error ${res.status}`;
          setPreview({ status: 'error', message: detail });
          return;
        }
        const contentType = (res.headers.get('content-type') || '').toLowerCase();
        if (contentType.startsWith('image/')) {
          setPreview({
            status: 'image',
            url: previewUrl,
            mime: contentType.split(';')[0] || selectedArtifact.mime,
          });
          return;
        }
        const payload = (await res.json()) as SandboxArtifactPreviewPayload;
        setPreview({ status: 'json', payload });
      })
      .catch((e) => {
        if (!cancelled) {
          setPreview({
            status: 'error',
            message: e instanceof Error ? e.message : 'Error al cargar vista previa',
          });
        }
      });

    return () => {
      cancelled = true;
    };
  }, [selectedArtifact, effectiveChatId]);

  const handleDeleteRun = async () => {
    if (!selectedRunId || !effectiveChatId.trim()) return;
    if (!window.confirm('¿Eliminar este run y todos sus artefactos?')) return;
    setBusy(true);
    try {
      await adminService.deleteSandboxRun(selectedRunId, effectiveChatId.trim());
      await loadRuns();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo eliminar el run');
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteArtifact = async () => {
    if (!selectedArtifact) return;
    if (!window.confirm(`¿Eliminar ${selectedArtifact.filename}?`)) return;
    setBusy(true);
    try {
      await adminService.deleteSandboxArtifact(
        selectedArtifact.artifact_id,
        effectiveChatId.trim()
      );
      await loadRuns();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo eliminar el artefacto');
    } finally {
      setBusy(false);
    }
  };

  const handleSaveToVault = async () => {
    if (!selectedArtifact) return;
    const dest = window.prompt(
      'Ruta en vault OUTPUT (relativa). Vacío = SandboxPromoted/nombre.ext',
      `SandboxPromoted/${selectedArtifact.filename}`
    );
    if (dest === null) return;
    setBusy(true);
    try {
      const res = await adminService.saveSandboxArtifactToVault({
        artifactId: selectedArtifact.artifact_id,
        chatId: effectiveChatId.trim(),
        relativeDest: dest.trim(),
        tenantId,
        projectId,
      });
      window.alert(`Guardado en vault:\n${res.relative_path}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar en Drive');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full min-h-0 flex-col rounded-2xl border border-slate-800 bg-slate-950 text-slate-100">
      <div className="shrink-0 border-b border-amber-900/50 bg-amber-950/40 px-4 py-2">
        <p className="text-[11px] text-amber-100">
          Scratch efímero del sandbox — no indexado en RAG hasta que uses{' '}
          <strong>Guardar en Drive</strong>.
        </p>
      </div>

      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-slate-800 px-4 py-2">
        <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
          <h2 className="text-sm font-semibold text-slate-100">Archivos generados</h2>
          {globalMode ? (
            <input
              type="text"
              value={chatFilter}
              onChange={(e) => setChatFilter(e.target.value)}
              placeholder="Filtrar por chat_id…"
              className="max-w-[200px] rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-[10px] font-mono text-slate-200"
            />
          ) : null}
        </div>
        <div className="flex items-center gap-2">
          {selectedRunId ? (
            <button
              type="button"
              disabled={busy}
              onClick={() => void handleDeleteRun()}
              className="inline-flex items-center gap-1 text-[10px] text-red-300 hover:text-red-200 disabled:opacity-50"
            >
              <Trash2 size={12} />
              Borrar run
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => void loadRuns()}
            className="inline-flex items-center gap-1 text-[10px] text-sky-400 hover:text-sky-300"
            disabled={loading}
          >
            <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
            Actualizar
          </button>
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <aside className="flex w-full shrink-0 flex-col border-b border-slate-800 lg:w-80 lg:border-b-0 lg:border-r">
          <div className="max-h-48 overflow-y-auto lg:max-h-none lg:flex-1">
            {loading ? (
              <p className="p-3 text-xs text-slate-500">Cargando runs…</p>
            ) : error ? (
              <p className="p-3 text-xs text-amber-300">{error}</p>
            ) : runs.length === 0 ? (
              <p className="p-3 text-xs text-slate-500">
                Sin artefactos. Ejecuta código en el sandbox desde{' '}
                <Link href="/playground" className="text-sky-400 hover:underline">
                  Chat
                </Link>
                .
              </p>
            ) : (
              <ul className="divide-y divide-slate-800/80">
                {runs.map((run) => {
                  const active = run.run_id === selectedRunId;
                  return (
                    <li key={`${run.chat_id}-${run.run_id}`}>
                      <button
                        type="button"
                        onClick={() => {
                          setSelectedRunId(run.run_id);
                          setSelectedRunChatId(String(run.chat_id || chatFilter || chatId));
                        }}
                        className={`w-full px-3 py-2 text-left text-xs transition ${
                          active ? 'bg-slate-800' : 'hover:bg-slate-900'
                        }`}
                      >
                        <div className="flex items-center justify-between gap-1">
                          <span className="truncate font-mono text-[10px]" title={run.run_id}>
                            {run.run_id.slice(0, 10)}…
                          </span>
                          <span
                            className={`rounded px-1 py-0.5 text-[9px] font-bold ${exitCodeBadge(run.exit_code)}`}
                          >
                            {run.exit_code ?? '—'}
                          </span>
                        </div>
                        <p className="mt-0.5 text-[10px] text-slate-500">
                          {formatUnixTime(run.created_at)} · {run.artifact_count} arch. ·{' '}
                          <span className="font-mono truncate">{run.chat_id || '—'}</span>
                        </p>
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>

          {selectedRunId ? (
            <div className="border-t border-slate-800">
              <p className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
                En este run
              </p>
              {artifactsLoading ? (
                <p className="px-3 pb-2 text-xs text-slate-500">Cargando…</p>
              ) : (
                <ul className="max-h-40 overflow-y-auto pb-2">
                  {artifacts.map((artifact) => {
                    const active = artifact.artifact_id === selectedArtifactId;
                    return (
                      <li key={artifact.artifact_id}>
                        <button
                          type="button"
                          onClick={() => setSelectedArtifactId(artifact.artifact_id)}
                          className={`flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs ${
                            active ? 'bg-slate-800' : 'hover:bg-slate-900'
                          }`}
                        >
                          {artifactIcon(artifact.mime, artifact.filename)}
                          <span className="min-w-0 flex-1 truncate">{artifact.filename}</span>
                          <span className="text-[10px] text-slate-500">
                            {formatBytes(artifact.byte_size)}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>
          ) : null}
        </aside>

        <div className="flex min-h-0 min-h-[240px] flex-1 flex-col">
          <PreviewPane
            artifact={selectedArtifact}
            chatId={effectiveChatId}
            preview={preview}
            busy={busy}
            onDelete={() => void handleDeleteArtifact()}
            onSaveToVault={() => void handleSaveToVault()}
          />
        </div>
      </div>
    </div>
  );
}
