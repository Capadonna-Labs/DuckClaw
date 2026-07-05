'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Database, FolderUp, RefreshCw, UploadCloud } from 'lucide-react';
import { adminService } from '@/services/adminService';
import type { KnowledgeSource, WorkspaceProjectSummary } from '@/services/adminService';
import { KnowledgePlaygroundBanner } from '@/components/knowledge/KnowledgePlaygroundBanner';
import { KnowledgeSourceCard } from '@/components/knowledge/KnowledgeSourceCard';
import {
  formatFolderPreviewLine,
  formatKnowledgeError,
  type KnowledgeFolderPreview,
} from '@/components/knowledge/knowledgeErrorMessage';

const ACCEPTED_EXTENSIONS = '.md,.markdown,.txt,.json,.csv,.pdf,.docx,.doc,.pptx,.html,.htm';
const DIRECTORY_INPUT_PROPS = { webkitdirectory: '', directory: '' };

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
  const [displayName, setDisplayName] = useState('');
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [computeEmbeddings, setComputeEmbeddings] = useState(true);
  const [folderPreview, setFolderPreview] = useState<KnowledgeFolderPreview | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [vaultRoots, setVaultRoots] = useState<{ path: string; label: string; exists: boolean }[]>([]);

  useEffect(() => {
    if (initialWorker) setWorkerUid(initialWorker);
  }, [initialWorker]);

  useEffect(() => {
    adminService
      .getKnowledgeConfig()
      .then((cfg) => {
        const roots = cfg.allowed_roots.filter((r) => r.exists);
        setVaultRoots(roots);
        if (roots.length === 1) {
          setServerPath(roots[0].path);
        }
      })
      .catch(() => setVaultRoots([]));
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

  const pollSourcesAfterImport = useCallback(
    async (previousCount: number) => {
      for (let attempt = 0; attempt < 6; attempt += 1) {
        await new Promise((resolve) => window.setTimeout(resolve, 3000));
        const rows = await loadSources();
        const indexing = rows.some((row) => row.status === 'indexing' || row.status === 'pending');
        if (rows.length > previousCount || (!indexing && rows.length > 0) || attempt >= 11) {
          break;
        }
      }
    },
    [loadSources]
  );

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
        display_name: displayName.trim() || undefined,
        compute_embeddings: computeEmbeddings,
      });
      setFiles([]);
      setDisplayName('');
      setNotice(`Carga lista: ${result.documents} docs, ${result.chunks} chunks.`);
      const prevCount = sources.length;
      await loadSources();
      if (result.documents > 0) {
        void pollSourcesAfterImport(prevCount);
      }
    } catch (e) {
      setError(formatKnowledgeError(e instanceof Error ? e.message : 'No se pudieron subir archivos'));
    } finally {
      setBusy(false);
    }
  }, [computeEmbeddings, displayName, files, loadSources, pollSourcesAfterImport, projectId, selectedProject?.name, sources.length, workerUid]);

  const previewServerPath = useCallback(async () => {
    if (!serverPath.trim()) return;
    setPreviewBusy(true);
    setError(null);
    setFolderPreview(null);
    try {
      const preview = await adminService.previewKnowledgeFolder(serverPath.trim());
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
        display_name: displayName.trim() || serverPath.split('/').filter(Boolean).pop() || 'Ruta servidor',
        source_kind: 'folder',
        project_id: projectId,
        worker_uid: workerUid,
        ingest: true,
        compute_embeddings: computeEmbeddings,
      });
      setServerPath('');
      setDisplayName('');
      setFolderPreview(null);
      const skipNote =
        (result.skipped_hidden ?? 0) > 0
          ? ` (${result.skipped_hidden} ocultos omitidos, ej. .obsidian)`
          : '';
      setNotice(
        result.status === 'indexing'
          ? `Indexando ${result.documents} documentos… La lista se actualizará sola.`
          : `Importación lista: ${result.documents} documento(s)${skipNote}. Sincronización automática activa.`
      );
      const prevCount = sources.length;
      await loadSources();
      void pollSourcesAfterImport(prevCount);
    } catch (e) {
      setError(formatKnowledgeError(e instanceof Error ? e.message : 'No se pudo importar la ruta servidor'));
    } finally {
      setBusy(false);
    }
  }, [computeEmbeddings, displayName, loadSources, pollSourcesAfterImport, projectId, serverPath, sources.length, workerUid]);

  const syncSource = useCallback(
    async (source: KnowledgeSource) => {
      setBusy(true);
      setError(null);
      setNotice(null);
      try {
        const result = await adminService.syncKnowledgeSource(source.source_id, {
          compute_embeddings: computeEmbeddings,
        });
        setNotice(
          `Sync: ${result.scanned} escaneados, ${result.upserted} actualizados, ${result.skipped} sin cambios, ${result.removed} eliminados.`
        );
        loadSources();
      } catch (e) {
        setError(e instanceof Error ? e.message : 'No se pudo sincronizar la fuente');
      } finally {
        setBusy(false);
      }
    },
    [computeEmbeddings, loadSources]
  );

  const deactivateSource = useCallback(
    async (source: KnowledgeSource) => {
      if (!window.confirm(`Desactivar fuente RAG "${source.display_name || source.source_uri}"?`)) return;
      setBusy(true);
      setError(null);
      try {
        await adminService.deleteKnowledgeSource(source.source_id);
        loadSources();
      } catch (e) {
        setError(e instanceof Error ? e.message : 'No se pudo desactivar la fuente');
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

      <section className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
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
        </div>

        <div className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
          <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">Nombre de la fuente</h2>
          <input
            value={displayName}
            onChange={(e) => setDisplayName(e.target.value)}
            placeholder="Ej. AWS Security Docs"
            className="mt-4 w-full rounded-xl border border-gov-blue-100 px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
          />
          <p className="mt-2 text-xs text-gov-gray-500 dark:text-dark-muted">
            Si lo dejas vacío, DuckClaw usará el nombre del proyecto o carpeta.
          </p>
        </div>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
          <h2 className="flex items-center gap-2 text-lg font-black text-gov-gray-900 dark:text-dark-text">
            <UploadCloud size={18} />
            Subir archivos desde tu PC
          </h2>
          <p className="mt-1 text-xs text-gov-gray-500 dark:text-dark-muted">
            Markdown, texto, JSON, CSV. PDF/Word si el servidor tiene{' '}
            <code className="font-mono text-[10px]">markitdown</code> instalado (
            <code className="font-mono text-[10px]">uv sync</code> o{' '}
            <code className="font-mono text-[10px]">duckops up</code>).
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
          <p className="mt-4 text-xs font-black uppercase tracking-wider text-gov-gray-500 dark:text-dark-muted">
            Seleccionar archivos
          </p>
          <input
            type="file"
            multiple
            accept={ACCEPTED_EXTENSIONS}
            onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            className="mt-2 w-full rounded-2xl border border-dashed border-gov-blue-200 p-5 text-sm dark:border-dark-border"
          />
          <p className="mt-4 text-xs font-black uppercase tracking-wider text-gov-gray-500 dark:text-dark-muted">
            Seleccionar carpeta
          </p>
          <input
            type="file"
            multiple
            {...DIRECTORY_INPUT_PROPS}
            onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
            className="mt-3 w-full rounded-2xl border border-dashed border-gov-blue-100 p-4 text-sm dark:border-dark-border"
          />
          {files.length > 0 && (
            <p className="mt-3 text-xs font-bold text-gov-gray-600 dark:text-dark-muted">
              {files.length} archivo(s) seleccionado(s)
            </p>
          )}
          <button
            type="button"
            onClick={() => void uploadFiles()}
            disabled={files.length === 0 || busy}
            className="mt-4 w-full rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-black text-white hover:bg-gov-blue-900 disabled:opacity-50"
          >
            Importar archivos
          </button>
        </div>

        <div className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
          <h2 className="flex items-center gap-2 text-lg font-black text-gov-gray-900 dark:text-dark-text">
            <FolderUp size={18} />
            Importar carpeta del servidor
          </h2>
          <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
            Ruta absoluta en este Mac (p. ej. carpeta de Obsidian o documentación). Se indexan .md, PDF y similares;
            carpetas ocultas como <code className="font-mono text-[10px]">.obsidian</code> se omiten.
          </p>
          <input
            value={serverPath}
            onChange={(e) => {
              setServerPath(e.target.value);
              setFolderPreview(null);
            }}
            placeholder="/Users/tu-usuario/Documentos/MiBiblioteca"
            className="mt-4 w-full rounded-xl border border-gov-blue-100 px-3 py-2 font-mono text-xs dark:border-dark-border dark:bg-dark-bg"
          />
          {vaultRoots.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-2">
              {vaultRoots.map((root) => (
                <button
                  key={root.path}
                  type="button"
                  onClick={() => {
                    setServerPath(root.path);
                    setFolderPreview(null);
                    setError(null);
                  }}
                  className="rounded-lg border border-gov-blue-200 bg-gov-blue-50 px-3 py-1.5 text-xs font-bold text-gov-blue-900 hover:bg-gov-blue-100 dark:border-dark-border dark:bg-dark-bg dark:text-dark-cyan"
                >
                  Usar {root.label}
                </button>
              ))}
            </div>
          )}
          {folderPreview && (
            <div className="mt-3 rounded-xl border border-gov-blue-50 bg-gov-blue-50/60 p-3 text-xs text-gov-gray-700 dark:border-dark-border dark:bg-dark-bg dark:text-dark-muted">
              <p className="font-bold">{formatFolderPreviewLine(folderPreview)}</p>
              {folderPreview.sample_paths.length > 0 && (
                <ul className="mt-2 space-y-0.5 font-mono text-[10px] opacity-80">
                  {folderPreview.sample_paths.map((path) => (
                    <li key={path} className="truncate">
                      {path}
                    </li>
                  ))}
                  {folderPreview.file_count > folderPreview.sample_paths.length && (
                    <li>… y {folderPreview.file_count - folderPreview.sample_paths.length} más</li>
                  )}
                </ul>
              )}
            </div>
          )}
          <label className="mt-3 flex cursor-pointer items-center gap-2 text-sm font-bold text-gov-gray-700 dark:text-dark-text">
            <input
              type="checkbox"
              checked={computeEmbeddings}
              onChange={(e) => setComputeEmbeddings(e.target.checked)}
              className="rounded border-gov-blue-200"
            />
            Búsqueda semántica al importar
          </label>
          <div className="mt-4 flex flex-col gap-2 sm:flex-row">
            <button
              type="button"
              onClick={() => void previewServerPath()}
              disabled={!serverPath.trim() || previewBusy || busy}
              className="flex-1 rounded-xl border border-gov-blue-200 px-4 py-2 text-sm font-black text-gov-blue-800 hover:bg-gov-blue-50 disabled:opacity-50 dark:border-dark-border dark:text-dark-cyan"
            >
              {previewBusy ? 'Comprobando…' : 'Comprobar carpeta'}
            </button>
            <button
              type="button"
              onClick={() => void importServerPath()}
              disabled={!serverPath.trim() || busy}
              className="flex-1 rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-black text-white hover:bg-gov-blue-900 disabled:opacity-50"
            >
              {busy ? 'Importando…' : 'Importar e indexar'}
            </button>
          </div>
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
              ? 'Aún no hay documentos para este proyecto. Sube archivos arriba.'
              : 'Aún no hay conocimiento global del framework. Sube archivos con alcance Framework.'}
          </p>
        ) : (
          <div className="mt-4 grid gap-3">
            {sources.map((source) => (
              <KnowledgeSourceCard
                key={source.source_id}
                source={source}
                projectId={projectId}
                busy={busy}
                onSync={(item) => void syncSource(item)}
                onDeactivate={(item) => void deactivateSource(item)}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
