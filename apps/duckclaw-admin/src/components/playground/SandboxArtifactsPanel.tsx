'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Braces,
  Download,
  File,
  FileImage,
  FileText,
  Loader2,
  RefreshCw,
  Table2,
} from 'lucide-react';
import {
  adminService,
  type SandboxArtifactMeta,
  type SandboxArtifactPreviewPayload,
  type SandboxRunSummary,
} from '@/services/adminService';
import { ChatMarkdown } from '@/components/chat/ChatMarkdown';

type SandboxArtifactsPanelProps = {
  chatId: string;
  refreshKey?: number;
  highlightRunId?: string;
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
    <div className="overflow-auto max-h-48 rounded-lg border border-slate-800">
      <table className="min-w-full text-[10px] text-slate-200">
        {headers.length > 0 ? (
          <thead className="bg-slate-900 sticky top-0">
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
    <pre className="max-h-48 overflow-auto rounded-lg border border-slate-800 bg-slate-950 p-2 text-[10px] font-mono text-slate-200 whitespace-pre-wrap">
      {text}
    </pre>
  );
}

function PreviewPane({
  artifact,
  chatId,
  preview,
}: {
  artifact: SandboxArtifactMeta | null;
  chatId: string;
  preview: PreviewState;
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
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-slate-800 px-3 py-2">
        <div className="min-w-0">
          <p className="truncate text-xs font-semibold text-slate-100" title={artifact.filename}>
            {artifact.filename}
          </p>
          <p className="text-[10px] text-slate-500">
            {artifact.mime || '—'} · {formatBytes(artifact.byte_size)}
          </p>
        </div>
        <a
          href={downloadUrl}
          download={artifact.filename}
          className="inline-flex shrink-0 items-center gap-1 rounded-md bg-sky-600 px-2 py-1 text-[10px] font-semibold text-white hover:bg-sky-500"
        >
          <Download size={12} aria-hidden />
          Descargar
        </a>
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
            className="max-h-56 w-full rounded-lg border border-slate-800 object-contain bg-slate-950"
          />
        ) : null}
        {preview.status === 'json' ? (
          <div className="space-y-2">
            {preview.payload.preview_kind === 'markdown' ? (
              <div className="rounded-lg border border-slate-800 bg-slate-950 p-2">
                <ChatMarkdown content={preview.payload.content ?? ''} className="text-xs prose-sm" />
              </div>
            ) : preview.payload.preview_kind === 'tabular' ||
              preview.payload.preview_kind === 'parquet' ? (
              <TabularPreview payload={preview.payload} />
            ) : (
              <JsonPreviewBody payload={preview.payload} />
            )}
            {preview.payload.truncated ? (
              <p className="text-[10px] text-slate-500">Vista truncada — descarga el archivo completo.</p>
            ) : null}
          </div>
        ) : null}
        {preview.status === 'idle' && !artifact.previewable ? (
          <p className="text-xs text-slate-500">Sin vista previa para este tipo. Usa Descargar.</p>
        ) : null}
      </div>
    </div>
  );
}

export function SandboxArtifactsPanel({
  chatId,
  refreshKey = 0,
  highlightRunId = '',
}: SandboxArtifactsPanelProps) {
  const [runs, setRuns] = useState<SandboxRunSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [selectedRunId, setSelectedRunId] = useState('');
  const [artifacts, setArtifacts] = useState<SandboxArtifactMeta[]>([]);
  const [artifactsLoading, setArtifactsLoading] = useState(false);
  const [selectedArtifactId, setSelectedArtifactId] = useState('');
  const [preview, setPreview] = useState<PreviewState>({ status: 'idle' });

  const selectedArtifact = useMemo(
    () => artifacts.find((a) => a.artifact_id === selectedArtifactId) ?? null,
    [artifacts, selectedArtifactId]
  );

  const loadRuns = useCallback(async () => {
    if (!chatId.trim()) {
      setRuns([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError('');
    try {
      const res = await adminService.listSandboxRuns(chatId.trim(), 20);
      const nextRuns = res.runs ?? [];
      setRuns(nextRuns);
      setSelectedRunId((prev) => {
        if (highlightRunId && nextRuns.some((r) => r.run_id === highlightRunId)) {
          return highlightRunId;
        }
        if (prev && nextRuns.some((r) => r.run_id === prev)) return prev;
        return nextRuns[0]?.run_id ?? '';
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudieron cargar las ejecuciones');
      setRuns([]);
      setSelectedRunId('');
    } finally {
      setLoading(false);
    }
  }, [chatId, highlightRunId]);

  useEffect(() => {
    void loadRuns();
  }, [loadRuns, refreshKey]);

  useEffect(() => {
    if (!selectedRunId || !chatId.trim()) {
      setArtifacts([]);
      setSelectedArtifactId('');
      return;
    }
    let cancelled = false;
    setArtifactsLoading(true);
    adminService
      .getSandboxRun(selectedRunId, chatId.trim())
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
  }, [selectedRunId, chatId, refreshKey]);

  useEffect(() => {
    if (!selectedArtifact || !chatId.trim()) {
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
      chatId.trim()
    );

    setPreview({ status: 'loading' });
    void fetch(previewUrl, { credentials: 'include', cache: 'no-store' })
      .then(async (res) => {
        if (cancelled) return;
        if (!res.ok) {
          const data = await res.json().catch(() => ({}));
          const detail =
            typeof data?.detail === 'string' ? data.detail : `Error ${res.status}`;
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
  }, [selectedArtifact, chatId]);

  return (
    <div className="flex h-full min-h-0 flex-col bg-slate-950 text-slate-100">
      <div className="shrink-0 border-b border-amber-900/50 bg-amber-950/40 px-3 py-2">
        <p className="text-[10px] font-semibold text-amber-200">
          Scratch efímero — no indexado en RAG.
        </p>
      </div>

      <div className="flex shrink-0 items-center justify-between gap-2 border-b border-slate-800 px-3 py-2">
        <h3 className="text-xs font-semibold text-slate-200">Ejecuciones sandbox</h3>
        <button
          type="button"
          onClick={() => void loadRuns()}
          className="inline-flex items-center gap-1 text-[10px] text-sky-400 hover:text-sky-300"
          disabled={loading}
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} aria-hidden />
          Actualizar
        </button>
      </div>

      <div className="max-h-36 shrink-0 overflow-y-auto border-b border-slate-800">
        {loading ? (
          <p className="p-3 text-xs text-slate-500">Cargando runs…</p>
        ) : error ? (
          <p className="p-3 text-xs text-amber-300">{error}</p>
        ) : runs.length === 0 ? (
          <p className="p-3 text-xs text-slate-500">
            Sin artefactos sandbox para esta conversación. Ejecuta código en el sandbox.
          </p>
        ) : (
          <table className="w-full text-left text-[10px]">
            <thead className="sticky top-0 bg-slate-900 text-slate-500">
              <tr>
                <th className="px-2 py-1.5 font-semibold">Run</th>
                <th className="px-2 py-1.5 font-semibold">Creado</th>
                <th className="px-2 py-1.5 font-semibold">Artef.</th>
                <th className="px-2 py-1.5 font-semibold">Exit</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => {
                const active = run.run_id === selectedRunId;
                return (
                  <tr key={run.run_id}>
                    <td colSpan={4} className="p-0">
                      <button
                        type="button"
                        onClick={() => setSelectedRunId(run.run_id)}
                        className={`flex w-full items-center gap-1 px-2 py-1.5 text-left transition ${
                          active ? 'bg-slate-800 text-white' : 'text-slate-300 hover:bg-slate-900'
                        }`}
                      >
                        <span className="min-w-0 flex-1 truncate font-mono" title={run.run_id}>
                          {run.run_id.slice(0, 8)}…
                        </span>
                        <span className="shrink-0 text-slate-500">{formatUnixTime(run.created_at)}</span>
                        <span className="shrink-0 w-8 text-center text-slate-400">
                          {run.artifact_count}
                        </span>
                        <span
                          className={`shrink-0 rounded px-1 py-0.5 text-[9px] font-bold ${exitCodeBadge(run.exit_code)}`}
                        >
                          {run.exit_code ?? '—'}
                        </span>
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {selectedRunId ? (
        <div className="shrink-0 border-b border-slate-800">
          <p className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-500">
            Artefactos
          </p>
          {artifactsLoading ? (
            <p className="px-3 pb-2 text-xs text-slate-500">Cargando…</p>
          ) : artifacts.length === 0 ? (
            <p className="px-3 pb-2 text-xs text-slate-500">Este run no tiene artefactos.</p>
          ) : (
            <ul className="max-h-28 overflow-y-auto px-1 pb-1">
              {artifacts.map((artifact) => {
                const active = artifact.artifact_id === selectedArtifactId;
                return (
                  <li key={artifact.artifact_id}>
                    <button
                      type="button"
                      onClick={() => setSelectedArtifactId(artifact.artifact_id)}
                      className={`flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-xs transition ${
                        active ? 'bg-slate-800 text-white' : 'text-slate-300 hover:bg-slate-900'
                      }`}
                    >
                      {artifactIcon(artifact.mime, artifact.filename)}
                      <span className="min-w-0 flex-1 truncate">{artifact.filename}</span>
                      <span className="shrink-0 text-[10px] text-slate-500">
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

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <PreviewPane artifact={selectedArtifact} chatId={chatId} preview={preview} />
      </div>
    </div>
  );
}
