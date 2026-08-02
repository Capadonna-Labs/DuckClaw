'use client';

import { useRef } from 'react';
import { HardDrive, MessageSquareText, UploadCloud } from 'lucide-react';
import type { WorkspaceProjectSummary } from '@/services/adminService';
import { KnowledgeFolderBrowser } from '@/components/knowledge/KnowledgeFolderBrowser';
import {
  formatFolderPreviewLine,
  type KnowledgeFolderPreview,
} from '@/components/knowledge/knowledgeErrorMessage';

const ACCEPTED_EXTENSIONS = '.md,.markdown,.txt,.json,.csv,.pdf,.docx,.doc,.pptx,.html,.htm';

type ProjectAgent = NonNullable<WorkspaceProjectSummary['agents']>[number];

export type KnowledgeControlPanelProps = {
  projects: WorkspaceProjectSummary[];
  projectId: string;
  workerUid: string;
  agents: ProjectAgent[];
  computeEmbeddings: boolean;
  serverPath: string;
  folderPreview: KnowledgeFolderPreview | null;
  previewBusy: boolean;
  busy: boolean;
  filesCount: number;
  allowedRootsConfigured: boolean | null;
  /** True when selected path already has a registered RAG source. */
  existingSourceForPath?: boolean;
  onProjectChange: (projectId: string) => void;
  onWorkerChange: (workerUid: string) => void;
  onComputeEmbeddingsChange: (value: boolean) => void;
  onSelectPath: (path: string) => void;
  onImport: () => void;
  onUploadFiles: () => void;
  onFilesSelected: (files: File[]) => void;
};

export function KnowledgeControlPanel({
  projects,
  projectId,
  workerUid,
  agents,
  computeEmbeddings,
  serverPath,
  folderPreview,
  previewBusy,
  busy,
  filesCount,
  allowedRootsConfigured,
  existingSourceForPath = false,
  onProjectChange,
  onWorkerChange,
  onComputeEmbeddingsChange,
  onSelectPath,
  onImport,
  onUploadFiles,
  onFilesSelected,
}: KnowledgeControlPanelProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const importLabel = existingSourceForPath
    ? busy
      ? 'Actualizando…'
      : 'Actualizar en el chat'
    : busy
      ? 'Añadiendo…'
      : 'Añadir al chat';

  return (
    <aside className="rounded-2xl border border-gov-gray-100 bg-white p-4 shadow-sm dark:border-dark-border dark:bg-dark-surface lg:sticky lg:top-4 space-y-5">
      <div className="space-y-3">
        <h2 className="text-sm font-black text-gov-gray-900 dark:text-dark-text">Alcance</h2>
        <p className="text-[11px] text-gov-gray-500 dark:text-dark-muted">
          Por defecto las carpetas van a la plataforma (todos los agentes). Acota solo si lo necesitas.
        </p>
        <label className="block text-xs font-bold text-gov-gray-700 dark:text-dark-text">
          Proyecto
          <select
            value={projectId}
            onChange={(e) => onProjectChange(e.target.value)}
            className="mt-1 w-full rounded-xl border border-gov-gray-200 px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
          >
            <option value="">Plataforma (todos los agentes)</option>
            {projects.map((project) => (
              <option key={project.project_id} value={project.project_id}>
                {project.name}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs font-bold text-gov-gray-700 dark:text-dark-text">
          Agente opcional
          <select
            value={workerUid}
            onChange={(e) => onWorkerChange(e.target.value)}
            disabled={!projectId}
            className="mt-1 w-full rounded-xl border border-gov-gray-200 px-3 py-2 text-sm disabled:opacity-60 dark:border-dark-border dark:bg-dark-bg"
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

      <div className="space-y-3 border-t border-gov-gray-100 pt-4 dark:border-dark-border">
        <h2 className="flex items-center gap-2 text-sm font-black text-gov-gray-900 dark:text-dark-text">
          <HardDrive size={16} />
          En disco
        </h2>
        <p className="text-[11px] leading-relaxed text-gov-gray-500 dark:text-dark-muted">
          Carpetas que el servidor puede leer. Elegir una ruta no la pone en búsqueda semántica del chat.
        </p>

        <label className="flex cursor-pointer items-center gap-2 text-xs font-bold text-gov-gray-700 dark:text-dark-text">
          <input
            type="checkbox"
            checked={computeEmbeddings}
            onChange={(e) => onComputeEmbeddingsChange(e.target.checked)}
            className="rounded border-gov-gray-300"
          />
          Búsqueda semántica al añadir al chat
        </label>

        {allowedRootsConfigured === false ? (
          <p className="rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-200">
            Configura <code className="font-mono">DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS</code> en{' '}
            <code className="font-mono">.env</code>.
          </p>
        ) : allowedRootsConfigured === true ? (
          <KnowledgeFolderBrowser
            selectedPath={serverPath}
            initialPath={serverPath}
            onSelect={onSelectPath}
          />
        ) : (
          <p className="text-xs text-gov-gray-500 dark:text-dark-muted">Comprobando rutas…</p>
        )}

        {serverPath.trim() ? (
          <p className="truncate font-mono text-[10px] text-gov-gray-500 dark:text-dark-muted">{serverPath}</p>
        ) : null}

        {previewBusy ? (
          <p className="text-xs text-gov-gray-500 dark:text-dark-muted">Comprobando archivos…</p>
        ) : null}

        {folderPreview && !previewBusy ? (
          <div className="rounded-xl border border-gov-gray-100 bg-gov-gray-50 p-2.5 text-xs text-gov-gray-700 dark:border-dark-border dark:bg-dark-bg dark:text-dark-muted">
            <p className="font-bold">{formatFolderPreviewLine(folderPreview)}</p>
            {folderPreview.sample_paths.length > 0 ? (
              <ul className="mt-1.5 space-y-0.5 font-mono text-[10px] opacity-80">
                {folderPreview.sample_paths.slice(0, 3).map((path) => (
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

        <div className="space-y-2 border-t border-gov-gray-100 pt-3 dark:border-dark-border">
          <h3 className="flex items-center gap-2 text-xs font-black text-gov-gray-900 dark:text-dark-text">
            <MessageSquareText size={14} />
            En el chat
          </h3>
          <p className="text-[11px] text-gov-gray-500 dark:text-dark-muted">
            Indexa la carpeta elegida para que los agentes la busquen en conversación.
          </p>
          <button
            type="button"
            onClick={onImport}
            disabled={
              !serverPath.trim() ||
              busy ||
              previewBusy ||
              !folderPreview ||
              folderPreview.file_count === 0
            }
            className="w-full rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-black text-white hover:bg-gov-blue-900 disabled:opacity-50"
          >
            {importLabel}
          </button>
        </div>

        <div className="space-y-2 border-t border-gov-gray-100 pt-3 dark:border-dark-border">
          <h3 className="flex items-center gap-2 text-xs font-black text-gov-gray-900 dark:text-dark-text">
            <UploadCloud size={14} />
            Subir archivos
          </h3>
          <input
            ref={fileInputRef}
            type="file"
            multiple
            accept={ACCEPTED_EXTENSIONS}
            className="sr-only"
            onChange={(e) => onFilesSelected(Array.from(e.target.files ?? []))}
          />
          <button
            type="button"
            onClick={() => fileInputRef.current?.click()}
            className="w-full rounded-xl border border-gov-gray-200 px-3 py-2 text-xs font-bold text-gov-blue-800 dark:border-dark-border dark:text-dark-cyan"
          >
            Elegir archivos
          </button>
          {filesCount > 0 ? (
            <p className="text-xs font-bold text-gov-gray-600 dark:text-dark-muted">
              {filesCount} archivo(s) seleccionado(s)
            </p>
          ) : null}
          <button
            type="button"
            onClick={onUploadFiles}
            disabled={filesCount === 0 || busy}
            className="w-full rounded-xl border border-gov-gray-200 px-3 py-2 text-xs font-bold text-gov-blue-800 disabled:opacity-50 dark:border-dark-border dark:text-dark-cyan"
          >
            Subir e indexar
          </button>
        </div>
      </div>
    </aside>
  );
}
