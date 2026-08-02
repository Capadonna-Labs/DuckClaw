'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Database } from 'lucide-react';
import { adminService } from '@/services/adminService';
import type { KnowledgeSource, WorkspaceProjectSummary } from '@/services/adminService';
import { KnowledgeControlPanel } from '@/components/knowledge/KnowledgeControlPanel';
import { KnowledgeScopeStatus, knowledgeScopeStatusVisible } from '@/components/knowledge/KnowledgeScopeStatus';
import { KnowledgeSourcesGrid } from '@/components/knowledge/KnowledgeSourcesGrid';
import {
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

function normalizeKnowledgeUri(uri: string): string {
  return uri.trim().replace(/\/+$/, '').toLowerCase();
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
  const [allowedRootsConfigured, setAllowedRootsConfigured] = useState<boolean | null>(null);

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

  const importServerPath = useCallback(async () => {
    if (!serverPath.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const pathKey = normalizeKnowledgeUri(serverPath);
      const existing = sources.find(
        (source) =>
          source.source_kind === 'folder' &&
          normalizeKnowledgeUri(source.source_uri || '') === pathKey
      );
      if (existing) {
        const result = await adminService.syncKnowledgeSource(existing.source_id, {
          compute_embeddings: computeEmbeddings,
        });
        setNotice(result.message ?? 'Actualización encolada…');
        void waitForKnowledgeJob(result.sync_job_id, 'Actualizando carpeta', {
          sourceId: existing.source_id,
        });
        return;
      }

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
          ? `Añadiendo al chat ${result.documents} documento(s)…`
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
  }, [
    computeEmbeddings,
    loadSources,
    projectId,
    serverPath,
    sources,
    waitForKnowledgeJob,
    workerUid,
  ]);

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
        setNotice('Fuente eliminada del RAG.');
        loadSources();
      } catch (e) {
        setError(e instanceof Error ? e.message : 'No se pudo eliminar la fuente del RAG');
      } finally {
        setBusy(false);
      }
    },
    [loadSources]
  );

  const handleSelectPath = useCallback(
    (path: string) => {
      setServerPath(path);
      setFolderPreview(null);
      setError(null);
      void previewServerPath(path);
    },
    [previewServerPath]
  );

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-3xl font-black text-gov-gray-900 dark:text-dark-text">
            <Database size={28} />
            Conocimiento
          </h1>
          <p className="mt-1 text-sm text-gov-gray-600 dark:text-dark-muted">
            En disco = lectura permitida. En el chat = indexado para búsqueda de los agentes.
          </p>
          {knowledgeScopeStatusVisible(sources, loading) ? (
            <div className="mt-2">
              <KnowledgeScopeStatus
                projectId={projectId}
                projectName={selectedProject?.name}
                workerId={workerUid || initialWorker}
                sources={sources}
                loading={loading}
              />
            </div>
          ) : null}
        </div>
        {projectId ? (
          <Link
            href={`/projects/${encodeURIComponent(projectId)}`}
            className="rounded-xl border border-gov-gray-200 px-4 py-2 text-sm font-bold text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:text-dark-cyan"
          >
            Ver proyecto
          </Link>
        ) : null}
      </header>

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

      <div className="grid gap-6 lg:grid-cols-12">
        <div className="lg:col-span-4">
          <KnowledgeControlPanel
            projects={projects}
            projectId={projectId}
            workerUid={workerUid}
            agents={agents}
            computeEmbeddings={computeEmbeddings}
            serverPath={serverPath}
            folderPreview={folderPreview}
            previewBusy={previewBusy}
            busy={busy}
            filesCount={files.length}
            allowedRootsConfigured={allowedRootsConfigured}
            existingSourceForPath={sources.some(
              (source) =>
                source.source_kind === 'folder' &&
                normalizeKnowledgeUri(source.source_uri || '') ===
                  normalizeKnowledgeUri(serverPath)
            )}
            onProjectChange={(value) => {
              setProjectId(value);
              setWorkerUid('');
            }}
            onWorkerChange={setWorkerUid}
            onComputeEmbeddingsChange={setComputeEmbeddings}
            onSelectPath={handleSelectPath}
            onImport={() => void importServerPath()}
            onUploadFiles={() => void uploadFiles()}
            onFilesSelected={setFiles}
          />
        </div>
        <div className="lg:col-span-8">
          <KnowledgeSourcesGrid
            projectId={projectId}
            sources={sources}
            loading={loading}
            busy={busy}
            indexingJobs={indexingJobs}
            onRefresh={() => void loadSources()}
            onSync={(item) => void syncSource(item)}
            onDelete={(item) => void deleteSource(item)}
          />
        </div>
      </div>
    </div>
  );
}
