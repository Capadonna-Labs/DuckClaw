'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { Database, FolderUp, RefreshCw, Trash2, UploadCloud } from 'lucide-react';
import { adminService } from '@/services/adminService';
import type { KnowledgeSource, WorkspaceProjectSummary } from '@/services/adminService';

const ACCEPTED_EXTENSIONS = '.md,.markdown,.txt,.json,.csv';
const DIRECTORY_INPUT_PROPS = { webkitdirectory: '', directory: '' };

export default function KnowledgePage() {
  const searchParams = useSearchParams();
  const initialProject = searchParams.get('project') || '';
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

  const loadSources = useCallback(() => {
    setLoading(true);
    setError(null);
    adminService
      .listKnowledgeSources({ project_id: projectId, worker_uid: workerUid })
      .then(setSources)
      .catch((e) => setError(e instanceof Error ? e.message : 'No se pudo cargar RAG'))
      .finally(() => setLoading(false));
  }, [projectId, workerUid]);

  useEffect(() => {
    loadSources();
  }, [loadSources]);

  const uploadFiles = useCallback(async () => {
    if (!projectId || files.length === 0) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const result = await adminService.uploadKnowledgeFiles({
        files,
        project_id: projectId,
        worker_uid: workerUid,
        display_name: displayName.trim() || selectedProject?.name || 'Carga RAG',
      });
      setFiles([]);
      setDisplayName('');
      setNotice(`Carga lista: ${result.documents} docs, ${result.chunks} chunks.`);
      loadSources();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudieron subir archivos');
    } finally {
      setBusy(false);
    }
  }, [displayName, files, loadSources, projectId, selectedProject?.name, workerUid]);

  const importServerPath = useCallback(async () => {
    if (!projectId || !serverPath.trim()) return;
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
        compute_embeddings: false,
      });
      setServerPath('');
      setDisplayName('');
      setNotice(`Ruta importada: ${result.documents} docs, ${result.chunks} chunks.`);
      loadSources();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo importar la ruta servidor');
    } finally {
      setBusy(false);
    }
  }, [displayName, loadSources, projectId, serverPath, workerUid]);

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
              Agentes / RAG
            </p>
            <h1 className="mt-2 flex items-center gap-2 text-3xl font-black text-gov-gray-900 dark:text-dark-text">
              <Database size={28} />
              Gestor RAG
            </h1>
            <p className="mt-2 max-w-3xl text-sm text-gov-gray-600 dark:text-dark-muted">
              Asocia conocimiento a un proyecto y, opcionalmente, a un agente. El Playground recupera estos chunks
              cuando conversa con `project_id`.
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

      <section className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
        <div className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
          <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">Scope</h2>
          <div className="mt-4 grid gap-3 md:grid-cols-2">
            <label className="block text-sm font-bold text-gov-gray-700 dark:text-dark-text">
              Proyecto
              <select
                value={projectId}
                onChange={(e) => {
                  setProjectId(e.target.value);
                  setWorkerUid('');
                }}
                className="mt-1 w-full rounded-xl border border-gov-blue-100 px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
              >
                <option value="">Selecciona un proyecto</option>
                {projects.map((project) => (
                  <option key={project.project_id} value={project.project_id}>
                    {project.name}
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
          <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
            Recomendado para empezar. Soporta Markdown, texto, JSON y CSV.
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
            disabled={!projectId || files.length === 0 || busy}
            className="mt-4 w-full rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-black text-white hover:bg-gov-blue-900 disabled:opacity-50"
          >
            Importar archivos
          </button>
        </div>

        <div className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
          <h2 className="flex items-center gap-2 text-lg font-black text-gov-gray-900 dark:text-dark-text">
            <FolderUp size={18} />
            Ruta servidor avanzada
          </h2>
          <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
            Para carpetas grandes ya disponibles en el host. Deben estar bajo `DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS`.
          </p>
          <input
            value={serverPath}
            onChange={(e) => setServerPath(e.target.value)}
            placeholder="/Users/workstation/docs/aws"
            className="mt-4 w-full rounded-xl border border-gov-blue-100 px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
          />
          <button
            type="button"
            onClick={() => void importServerPath()}
            disabled={!projectId || !serverPath.trim() || busy}
            className="mt-4 w-full rounded-xl border border-gov-blue-200 px-4 py-2 text-sm font-black text-gov-blue-800 hover:bg-gov-blue-50 disabled:opacity-50 dark:border-dark-border dark:text-dark-cyan"
          >
            Importar ruta servidor
          </button>
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

      <section className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">Fuentes registradas</h2>
          <button
            type="button"
            onClick={loadSources}
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
            Sin fuentes RAG para este scope.
          </p>
        ) : (
          <div className="mt-4 grid gap-3">
            {sources.map((source) => (
              <div
                key={source.source_id}
                className="flex flex-col gap-3 rounded-2xl border border-gov-blue-50 p-4 dark:border-dark-border md:flex-row md:items-center md:justify-between"
              >
                <div className="min-w-0">
                  <p className="font-black text-gov-gray-900 dark:text-dark-text">
                    {source.display_name || source.source_uri}
                  </p>
                  <p className="mt-1 truncate font-mono text-[11px] text-gov-gray-500 dark:text-dark-muted">
                    {source.source_uri}
                  </p>
                  <p className="mt-2 text-xs text-gov-gray-500 dark:text-dark-muted">
                    {source.status} · {source.document_count} docs · {source.chunk_count} chunks
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => void deactivateSource(source)}
                  disabled={busy}
                  className="inline-flex items-center justify-center gap-2 rounded-xl border border-red-200 px-3 py-2 text-xs font-bold text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-900/60 dark:text-red-300"
                >
                  <Trash2 size={14} />
                  Desactivar
                </button>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
