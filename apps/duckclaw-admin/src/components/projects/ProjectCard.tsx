'use client';

import Link from 'next/link';
import { Eye, Power, RotateCcw, Trash2 } from 'lucide-react';
import type { WorkspaceProjectSummary } from '@/services/adminService';

export type ProjectCardProps = {
  project: WorkspaceProjectSummary;
  canWrite: boolean;
  onDelete: (project: WorkspaceProjectSummary) => void;
  onDeactivate: (project: WorkspaceProjectSummary) => void;
  onReactivate: (project: WorkspaceProjectSummary) => void;
};

function formatUpdatedAt(value?: string): string | null {
  if (!value) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString();
}

export function ProjectCard({
  project,
  canWrite,
  onDelete,
  onDeactivate,
  onReactivate,
}: ProjectCardProps) {
  const updatedLabel = formatUpdatedAt(project.updated_at);
  const inactive = project.status === 'inactive';

  return (
    <article className="flex min-h-[150px] flex-col rounded-2xl border border-gov-gray-100 bg-white p-3.5 shadow-sm transition-all hover:border-gov-blue-200 dark:border-dark-border dark:bg-dark-surface">
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-2">
          <p className="min-w-0 flex-1 truncate text-sm font-black text-gov-gray-900 dark:text-dark-text" title={project.name}>
            {project.name}
          </p>
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-black uppercase ${
              inactive
                ? 'bg-gov-gray-100 text-gov-gray-600 dark:bg-dark-bg dark:text-dark-muted'
                : 'bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200'
            }`}
          >
            {project.status}
          </span>
        </div>
        <p className="mt-1.5 text-xs text-gov-gray-500 dark:text-dark-muted">
          {project.agent_count ?? 0} agente{(project.agent_count ?? 0) === 1 ? '' : 's'}
          {updatedLabel ? <> · act. {updatedLabel}</> : null}
        </p>
        {project.description ? (
          <p className="mt-1 line-clamp-2 text-xs text-gov-gray-500 dark:text-dark-muted">{project.description}</p>
        ) : null}
      </div>

      <div className="mt-auto flex flex-wrap items-center justify-end gap-1.5 border-t border-gov-gray-100 pt-2.5 dark:border-dark-border">
        <Link
          href={`/projects/${encodeURIComponent(project.project_id)}`}
          className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-2.5 py-1.5 text-xs font-bold text-gov-blue-800 dark:border-dark-border dark:text-dark-cyan"
          title="Ver proyecto"
        >
          <Eye size={14} />
          Abrir
        </Link>
        {!inactive ? (
          <Link
            href={`/playground?project=${encodeURIComponent(project.project_id)}`}
            className="inline-flex items-center rounded-lg border border-gov-gray-200 px-2.5 py-1.5 text-xs font-bold text-gov-blue-800 dark:border-dark-border dark:text-dark-cyan"
          >
            Chat
          </Link>
        ) : null}
        {canWrite ? (
          <>
            {inactive ? (
              <button
                type="button"
                onClick={() => onReactivate(project)}
                className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-2.5 py-1.5 text-xs font-bold text-gov-blue-800 dark:border-dark-border dark:text-dark-cyan"
                title="Activar proyecto"
              >
                <RotateCcw size={14} />
              </button>
            ) : (
              <button
                type="button"
                onClick={() => onDeactivate(project)}
                className="inline-flex items-center gap-1 rounded-lg border border-amber-200 px-2.5 py-1.5 text-xs font-bold text-amber-700 dark:border-amber-900/60 dark:text-amber-300"
                title="Desactivar proyecto"
              >
                <Power size={14} />
              </button>
            )}
            <button
              type="button"
              onClick={() => onDelete(project)}
              className="inline-flex items-center gap-1 rounded-lg border border-red-200 px-2.5 py-1.5 text-xs font-bold text-red-700 dark:border-red-900/60 dark:text-red-300"
              title="Eliminar definitivo"
              aria-label="Eliminar definitivo"
            >
              <Trash2 size={14} />
            </button>
          </>
        ) : null}
      </div>
    </article>
  );
}
