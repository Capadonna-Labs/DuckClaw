'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Database, RefreshCw, UploadCloud } from 'lucide-react';
import { adminService } from '@/services/adminService';
import type { KnowledgeSource, WorkspaceProjectSummary } from '@/services/adminService';
import { KnowledgeFolderBrowser } from '@/components/knowledge/KnowledgeFolderBrowser';
import { KnowledgePlaygroundBanner } from '@/components/knowledge/KnowledgePlaygroundBanner';
import { KnowledgeSourceCard } from '@/components/knowledge/KnowledgeSourceCard';
import {
  formatFolderPreviewLine,
  formatKnowledgeError,
  type KnowledgeFolderPreview,
} from '@/components/knowledge/knowledgeErrorMessage';
import {
  formatKnowledgeJobPollNotice,
  pollKnowledgeSyncJob,
  type KnowledgeJobProgress,
} from '@/lib/pollKnowledgeSyncJob';

type IndexingJobState = {
  jobId?: string;
  expectedFiles?: number;
  progress?: KnowledgeJobProgress;
  jobStatus?: string | null;
  errorMessage?: string | null;
};

const ACCEPTED_EXTENSIONS = '.md,.markdown,.txt,.json,.csv,.pdf,.docx,.doc,.pptx,.html,.htm';

function defaultSourceLabel(serverPath: string, files: File[]): string {
  const path = serverPath.trim();
  if (path) {
    return path.split('/').filter(Boolean).pop() || 'Carpeta';
  }
  const first = files[0];
  if (!first) return 'Documentos';
  const relative = (first as File & { webkitRelativePath?: string }).webkitRelativePath?.trim();
  if (relative) {
    const top = relative.split('/').filter(Boolean)[0];
    if (top) return top;
  }
  const base = first.name.replace(/\.[^.]+$/, '').trim();
  return base || 'Documentos';
}

export default function KnowledgePage() {
  const searchParams = useSearchParams();
  const initialProject = searchParams.get('project') || '';
  const initialWorker = searchParams.get('worker') || '';
  const [projects, setProjects] = useState<WorkspaceProjectSummary[]>([]);
  const [projectDetail, setProjectDetail] = useState<WorkspaceProjectSummary | null>(null);
  const [projectId, setProjectId] = useState(initialProject);
  const [workerUid, setWorkerUid] = useState('');
  const [sources, setSources] = useState<KnowledgeSource[]>([]);
  const [files, setFiles] = useState<File[]>([]);
  const [serverPath, setServerPath] = useState('');
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [computeEmbeddings, setComputeEmbeddings] = useState(true);
  const [folderPreview, setFolderPreview] = useState<KnowledgeFolderPreview | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [indexingJobs, setIndexingJobs] = useState<Record<string, IndexingJobState>>({});
  const [looseUploadOpen, setLooseUploadOpen] = useState(false);
  const [allowedRootsConfigured, setAllowedRootsConfigured] = useState<boolean | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (initialWorker) setWorkerUid(initialWorker);
  }, [initialWorker]);

  useEffect(() => {
    adminService
      .getKnowledgeConfig()
      .then((config) => {
        const roots = config.allowed_roots ?? [];
        setAllowedRootsConfigured(roots.some((root) => root.exists));
      })
      .catch(() => setAllowedRootsConfigured(false));
  }, []);

  useEffect(() => {
    adminService
      .listWorkspaceProjectsPage({ status: 'all', limit: 200 })
      .then((page) => setProjects(page.projects))
      .catch((e) => setError(e instanceof Error ? e.message : 'No se pudieron cargar proyectos'));
  }, []);

  const selectedProject = useMemo(
    () => projectDetail ?? projects.find((project) => project.project_id === projectId),
    [projectDetail, projectId, projects]
  );
  const agents = selectedProject?.agents ?? [];

  useEffect(() => {
    if (!projectId) {
      setProjectDetail(null);
      return;
    }
    adminService
      .getWorkspaceProject(projectId)
      .then((detail) => setProjectDetail(detail.project))
      .catch(() => setProjectDetail(projects.find((project) => project.project_id === projectId) ?? null));
  }, [projectId, projects]);

  const loadSources = useCallback(async (): Promise<KnowledgeSource[]> => {
    setLoading(true);
    setError(null);
    try {
      const rows = await adminService.listKnowledgeSources({ project_id: projectId, worker_uid: workerUid });
      setSources(rows);
      return rows;
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo cargar RAG');
      return [];
    } finally {
      setLoading(false);
    }
  }, [projectId, workerUid]);

  const loadSourcesSilent = useCallback(async () => {
    try {
      const rows = await adminService.listKnowledgeSources({ project_id: projectId, worker_uid: workerUid });
      setSources(rows);
    } catch {
      /* polling silencioso */
    }
  }, [projectId, workerUid]);

  const waitForKnowledgeJob = useCallback(
    async (
      jobId: string | undefined,
      busyLabel: string,
      options?: { sourceId?: string; expectedFiles?: number }
    ) => {
      const sourceId = options?.sourceId;
      if (!jobId) {
        await loadSources();
        return;
      }
      if (sourceId) {
        setIndexingJobs((prev) => ({
          ...prev,
          [sourceId]: { jobId, expectedFiles: options?.expectedFiles, progress: prev[sourceId]?.progress },
        }));
      }
      setNotice(`${busyLabel}…`);
      const pollResult = await pollKnowledgeSyncJob(jobId, {
        onTick: (status, progress) => {
          if (status === 'running' || status === 'queued') {
            const pct =
              progress?.files_total && progress.files_done !== undefined
                ? ` · ${progress.files_done}/${progress.files_total}`
                : '';
            setNotice(`${busyLabel} (${status})${pct}…`);
          }
          if (sourceId && progress) {
            setIndexingJobs((prev) => ({
              ...prev,
              [sourceId]: {
                jobId,
                expectedFiles: options?.expectedFiles,
                progress,
              },
            }));
          }
        },
      });
      if (sourceId) {
        setIndexingJobs((prev) => {
          const next = { ...prev };
          delete next[sourceId];
          return next;
        });
      }
      await loadSources();
      setNotice(formatKnowledgeJobPollNotice(pollResult, busyLabel));
    },
    [loadSources]
  );

  useEffect(() => {
    const indexing = sources.filter((source) => source.status === 'indexing');
    if (indexing.length === 0) return;

    const poll = async () => {
      await Promise.all(
        indexing.map(async (source) => {
          const row = await adminService.getKnowledgeSourceIndexingProgress(source.source_id).catch(() => null);
          if (!row?.active) return;
          setIndexingJobs((prev) => ({
            ...prev,
            [source.source_id]: {
              jobId: row.job_id ?? undefined,
              expectedFiles: row.file_count ?? prev[source.source_id]?.expectedFiles,
              progress: row.progress ?? prev[source.source_id]?.progress,
              jobStatus: row.job_status ?? prev[source.source_id]?.jobStatus,
              errorMessage: row.error_message ?? prev[source.source_id]?.errorMessage,
            },
          }));
        })
      );
    };

    void poll();
    const progressTimer = window.setInterval(() => {
      void poll();
    }, 2000);
    const sourcesTimer = window.setInterval(() => {
      void loadSourcesSilent();
    }, 5000);
    return () => {
      window.clearInterval(progressTimer);
      window.clearInterval(sourcesTimer);
    };
  }, [sources, loadSourcesSilent]);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  const uploadFiles = useCallback(async () => {
    if (files.length === 0) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await adminService.uploadKnowledgeFiles({
        files,
        project_id: projectId,
        worker_uid: workerUid,
        display_name: defaultSourceLabel('', files),
        compute_embeddings: computeEmbeddings,
      });
      setFiles([]);
      setNotice(`Carga encolada: ${result.documents} documento(s).`);
      await loadSources();
      void waitForKnowledgeJob(result.sync_job_id, 'Indexando carga', {
        sourceId: result.source_id,
        expectedFiles: result.documents,
      });
    } catch (e) {
      setError(formatKnowledgeError(e instanceof Error ? e.message : 'No se pudieron subir archivos'));
    } finally {
      setBusy(false);
    }
  }, [computeEmbeddings, files, loadSources, projectId, waitForKnowledgeJob, workerUid]);

  const previewServerPath = useCallback(async (pathOverride?: string) => {
    const path = (pathOverride ?? serverPath).trim();
    if (!path) return;
    setPreviewBusy(true);
    setError(null);
    setFolderPreview(null);
    try {
      const preview = await adminService.previewKnowledgeFolder(path);
      setFolderPreview(preview);
      if (preview.file_count === 0) {
        setError('No hay archivos .md/.txt/.pdf indexables en esa carpeta.');
      }
    } catch (e) {
      setError(formatKnowledgeError(e instanceof Error ? e.message : 'No se pudo comprobar la carpeta'));
    } finally {
      setPreviewBusy(false);
    }
  }, [serverPath]);

  const importServerPath = useCallback(async () => {
    if (!serverPath.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await adminService.createKnowledgeSource({
        source_uri: serverPath.trim(),
        display_name: defaultSourceLabel(serverPath, []),
        source_kind: 'folder',
        project_id: projectId,
        worker_uid: workerUid,
        ingest: true,
        compute_embeddings: computeEmbeddings,
      });
      setServerPath('');
      setFolderPreview(null);
      setNotice(
        result.status === 'indexing'
          ? `Indexando ${result.documents} documento(s)…`
          : `Importación encolada: ${result.documents} documento(s).`
      );
      await loadSources();
      void waitForKnowledgeJob(result.sync_job_id, 'Indexando carpeta', {
        sourceId: result.source_id,
        expectedFiles: result.documents,
      });
    } catch (e) {
      setError(formatKnowledgeError(e instanceof Error ? e.message : 'No se pudo importar la ruta servidor'));
    } finally {
      setBusy(false);
    }
  }, [computeEmbeddings, loadSources, projectId, serverPath, waitForKnowledgeJob, workerUid]);

  const syncSource = useCallback(
    async (source: KnowledgeSource) => {
      setBusy(true);
      setError(null);
      setNotice(null);
      try {
        const result = await adminService.syncKnowledgeSource(source.source_id, {
          compute_embeddings: computeEmbeddings,
        });
        setNotice(result.message ?? 'Sincronización encolada…');
        void waitForKnowledgeJob(result.sync_job_id, 'Sincronizando carpeta', {
          sourceId: source.source_id,
        });
      } catch (e) {
        setError(e instanceof Error ? e.message : 'No se pudo sincronizar la fuente');
      } finally {
        setBusy(false);
      }
    },
    [computeEmbeddings, waitForKnowledgeJob]
  );

  const deleteSource = useCallback(
    async (source: KnowledgeSource) => {
      if (
        !window.confirm(
          `Eliminar "${source.display_name || source.source_uri}" del RAG?\n\nSe borrarán del contexto del chat los ${source.document_count} documento(s) y ${source.chunk_count} fragmento(s) indexados. La carpeta original en disco no se toca.`
        )
      ) {
        return;
      }
      setBusy(true);
      setError(null);
      try {
        await adminService.deleteKnowledgeSource(source.source_id);
        setNotice('Fuente eliminada del RAG. El agente ya no verá esos documentos en el chat.');
        loadSources();
      } catch (e) {
        setError(e instanceof Error ? e.message : 'No se pudo eliminar la fuente del RAG');
      } finally {
        setBusy(false);
      }
    },
    [loadSources]
  );

  return (
    <div className="space-y-6">
      <header className="rounded-3xl border border-gov-blue-100 bg-white p-6 dark:border-dark-border dark:bg-dark-surface">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-xs font-black uppercase tracking-widest text-gov-blue-700 dark:text-dark-cyan">
              Conocimiento
            </p>
            <h1 className="mt-2 flex items-center gap-2 text-3xl font-black text-gov-gray-900 dark:text-dark-text">
              <Database size={28} />
              Documentos para tus agentes
            </h1>
            <p className="mt-2 max-w-3xl text-sm text-gov-gray-600 dark:text-dark-muted">
              Sube manuales, políticas o notas. Los agentes los consultan al responder en el chat.
              El alcance <strong>Plataforma</strong> aplica a todos; el de <strong>Proyecto</strong> solo
              a ese equipo.
            </p>
          </div>
          {projectId && (
            <Link
              href={`/projects/${encodeURIComponent(projectId)}`}
              className="rounded-xl border border-gov-blue-200 px-4 py-2 text-sm font-black text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:text-dark-cyan"
            >
              Ver proyecto
            </Link>
          )}
        </div>
      </header>

      <KnowledgePlaygroundBanner
        projectId={projectId}
        projectName={selectedProject?.name}
        workerId={workerUid || initialWorker}
        sources={sources}
        loading={loading}
      />

      <section className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
        <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">Alcance</h2>
        <div className="mt-4 grid gap-3 md:grid-cols-2">
          <label className="block text-sm font-bold text-gov-gray-700 dark:text-dark-text">
            Alcance
            <select
              value={projectId}
              onChange={(e) => {
                setProjectId(e.target.value);
                setWorkerUid('');
              }}
              className="mt-1 w-full rounded-xl border border-gov-blue-100 px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
            >
              <option value="">Plataforma (todos los agentes)</option>
              {projects.map((project) => (
                <option key={project.project_id} value={project.project_id}>
                  Proyecto: {project.name}
                </option>
              ))}
            </select>
          </label>

          <label className="block text-sm font-bold text-gov-gray-700 dark:text-dark-text">
            Agente opcional
            <select
              value={workerUid}
              onChange={(e) => setWorkerUid(e.target.value)}
              disabled={!projectId}
              className="mt-1 w-full rounded-xl border border-gov-blue-100 px-3 py-2 text-sm disabled:opacity-60 dark:border-dark-border dark:bg-dark-bg"
            >
              <option value="">Todo el proyecto</option>
              {agents.map((agent) => (
                <option key={agent.worker_uid} value={agent.worker_uid}>
                  {agent.display_name || agent.worker_id}
                </option>
              ))}
            </select>
            <p className="mt-1 text-xs font-normal text-gov-gray-500 dark:text-dark-muted">
              «Todo el proyecto» = RAG compartido por todos los agentes. Si falla, elige un agente concreto.
            </p>
          </label>
        </div>
      </section>

      <section className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
        <h2 className="flex items-center gap-2 text-lg font-black text-gov-gray-900 dark:text-dark-text">
          <UploadCloud size={18} />
          Agregar documentos
        </h2>
        <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
          Navega las carpetas permitidas en el servidor y elige una para indexar. Los agentes la consultarán en el chat.
        </p>

        <label className="mt-4 flex cursor-pointer items-center gap-2 text-sm font-bold text-gov-gray-700 dark:text-dark-text">
          <input
            type="checkbox"
            checked={computeEmbeddings}
            onChange={(e) => setComputeEmbeddings(e.target.checked)}
            className="rounded border-gov-blue-200"
          />
          Búsqueda semántica (embeddings)
        </label>
        <p className="mt-1 text-xs text-gov-gray-500 dark:text-dark-muted">
          Recomendado activado. Si lo apagas, solo busca por palabras exactas.
        </p>

        <div className="mt-4 space-y-4">
          {allowedRootsConfigured === false ? (
            <p className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-200">
              Configura <code className="font-mono">DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS</code> en{' '}
              <code className="font-mono">.env</code> y ejecuta{' '}
              <code className="font-mono">uv run duckops stack deploy</code>.
            </p>
          ) : allowedRootsConfigured === true ? (
            <KnowledgeFolderBrowser
              selectedPath={serverPath}
              initialPath={serverPath}
              onSelect={(path) => {
                setServerPath(path);
                setFolderPreview(null);
                setError(null);
                void previewServerPath(path);
              }}
            />
          ) : (
            <p className="text-xs text-gov-gray-500 dark:text-dark-muted">Comprobando rutas permitidas…</p>
          )}

          {serverPath.trim() ? (
            <p className="truncate font-mono text-[11px] text-gov-gray-600 dark:text-dark-muted">{serverPath}</p>
          ) : null}

          {previewBusy ? (
            <p className="text-xs text-gov-gray-500 dark:text-dark-muted">Comprobando archivos indexables…</p>
          ) : null}

          {folderPreview && !previewBusy ? (
            <div className="rounded-xl border border-gov-blue-50 bg-gov-blue-50/60 p-3 text-xs text-gov-gray-700 dark:border-dark-border dark:bg-dark-bg dark:text-dark-muted">
              <p className="font-bold">{formatFolderPreviewLine(folderPreview)}</p>
              {folderPreview.sample_paths.length > 0 ? (
                <ul className="mt-2 space-y-0.5 font-mono text-[10px] opacity-80">
                  {folderPreview.sample_paths.map((path) => (
                    <li key={path} className="truncate">
                      {path}
                    </li>
                  ))}
                  {folderPreview.file_count > folderPreview.sample_paths.length ? (
                    <li>… y {folderPreview.file_count - folderPreview.sample_paths.length} más</li>
                  ) : null}
                </ul>
              ) : null}
            </div>
          ) : null}

          <button
            type="button"
            onClick={() => void importServerPath()}
            disabled={
              !serverPath.trim() ||
              busy ||
              previewBusy ||
              !folderPreview ||
              folderPreview.file_count === 0
            }
            className="w-full rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-black text-white hover:bg-gov-blue-900 disabled:opacity-50"
          >
            {busy ? 'Indexando…' : 'Indexar'}
          </button>
        </div>

        <div className="mt-6 border-t border-gov-blue-50 pt-4 dark:border-dark-border">
          <button
            type="button"
            onClick={() => setLooseUploadOpen((open) => !open)}
            className="text-xs font-bold text-gov-blue-800 hover:underline dark:text-dark-cyan"
            aria-expanded={looseUploadOpen}
          >
            {looseUploadOpen ? '▾' : '▸'} Subir archivos sueltos (opcional)
          </button>
          {looseUploadOpen ? (
            <div className="mt-3 space-y-3">
              <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
                Markdown, texto, JSON, CSV. PDF/Word si markitdown está instalado en el host.
              </p>
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept={ACCEPTED_EXTENSIONS}
                className="sr-only"
                onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
              />
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                className="inline-flex w-full items-center justify-center rounded-xl border border-gov-blue-200 px-4 py-2 text-sm font-black text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:text-dark-cyan"
              >
                Elegir archivos
              </button>
              {files.length > 0 ? (
                <p className="text-xs font-bold text-gov-gray-600 dark:text-dark-muted">
                  {files.length} archivo(s) seleccionado(s)
                </p>
              ) : null}
              <button
                type="button"
                onClick={() => void uploadFiles()}
                disabled={files.length === 0 || busy}
                className="w-full rounded-xl border border-gov-blue-200 px-4 py-2 text-sm font-black text-gov-blue-800 hover:bg-gov-blue-50 disabled:opacity-50 dark:border-dark-border dark:text-dark-cyan"
              >
                Subir e indexar
              </button>
            </div>
          ) : null}
        </div>
      </section>

      {(error || notice) && (
        <div
          className={`rounded-2xl border p-4 text-sm ${
            error
              ? 'border-red-200 bg-red-50 text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300'
              : 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-300'
          }`}
        >
          {error || notice}
        </div>
      )}

      <section className="rounded-3xl border border-gov-blue-100 bg-white p-4 sm:p-5 dark:border-dark-border dark:bg-dark-surface overflow-hidden">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text min-w-0">Fuentes registradas</h2>
          <button
            type="button"
            onClick={() => void loadSources()}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-xl border border-gov-blue-100 px-3 py-2 text-xs font-bold text-gov-blue-800 disabled:opacity-50 dark:border-dark-border dark:text-dark-cyan"
          >
            <RefreshCw size={14} />
            Refrescar
          </button>
        </div>
        {loading ? (
          <p className="mt-4 text-sm text-gov-gray-500 dark:text-dark-muted">Cargando fuentes RAG...</p>
        ) : sources.length === 0 ? (
          <p className="mt-4 rounded-2xl border border-dashed border-gov-blue-100 p-4 text-sm text-gov-gray-500 dark:border-dark-border dark:text-dark-muted">
            {projectId
              ? 'Aún no hay documentos para este proyecto. Elige una carpeta arriba.'
              : 'Aún no hay conocimiento global. Elige una carpeta con alcance Plataforma.'}
          </p>
        ) : (
          <div className="mt-4 grid gap-3">
            {sources.map((source) => (
              <KnowledgeSourceCard
                key={source.source_id}
                source={source}
                projectId={projectId}
                busy={busy}
                jobProgress={indexingJobs[source.source_id]?.progress}
                expectedFileTotal={
                  indexingJobs[source.source_id]?.expectedFiles ??
                  (typeof source.metadata?.file_count === 'number' ? source.metadata.file_count : undefined)
                }
                jobStatus={indexingJobs[source.source_id]?.jobStatus}
                errorMessage={indexingJobs[source.source_id]?.errorMessage}
                onSync={(item) => void syncSource(item)}
                onDelete={(item) => void deleteSource(item)}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
