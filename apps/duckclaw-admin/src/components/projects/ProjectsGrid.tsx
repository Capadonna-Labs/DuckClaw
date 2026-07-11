'use client';

import Link from 'next/link';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { WorkspaceProjectSummary } from '@/services/adminService';
import { ProjectCard } from '@/components/projects/ProjectCard';

export type ProjectsGridProps = {
  projects: WorkspaceProjectSummary[];
  total: number;
  page: number;
  pageCount: number;
  canWrite: boolean;
  onPrevPage: () => void;
  onNextPage: () => void;
  onDelete: (project: WorkspaceProjectSummary) => void;
  onDeactivate: (project: WorkspaceProjectSummary) => void;
  onReactivate: (project: WorkspaceProjectSummary) => void;
};

export function ProjectsGrid({
  projects,
  total,
  page,
  pageCount,
  canWrite,
  onPrevPage,
  onNextPage,
  onDelete,
  onDeactivate,
  onReactivate,
}: ProjectsGridProps) {
  return (
    <section className="min-w-0 space-y-4">
      {total > 0 ? (
        <p className="text-xs text-gov-gray-500 dark:text-dark-muted">
          {total} proyecto{total === 1 ? '' : 's'} · página {page}/{pageCount}
        </p>
      ) : null}

      {projects.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-gov-gray-200 p-8 text-center dark:border-dark-border">
          <p className="text-sm font-bold text-gov-gray-700 dark:text-dark-text">Sin proyectos en esta vista</p>
          <p className="mt-1 text-xs text-gov-gray-500 dark:text-dark-muted">
            Ajusta filtros o crea uno desde el panel izquierdo.
          </p>
          {canWrite ? (
            <Link
              href="/projects/orchestrator"
              className="mt-4 inline-flex rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-black text-white hover:bg-gov-blue-900"
            >
              Crear proyecto
            </Link>
          ) : null}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-[repeat(auto-fill,minmax(min(100%,220px),1fr))] gap-3">
            {projects.map((project) => (
              <ProjectCard
                key={project.project_id}
                project={project}
                canWrite={canWrite}
                onDelete={onDelete}
                onDeactivate={onDeactivate}
                onReactivate={onReactivate}
              />
            ))}
          </div>
          <div className="flex items-center justify-end gap-2">
            <button
              type="button"
              disabled={page <= 1}
              onClick={onPrevPage}
              className="inline-flex items-center gap-1 rounded-xl border border-gov-gray-200 px-3 py-2 text-xs font-bold disabled:opacity-40 dark:border-dark-border"
            >
              <ChevronLeft size={14} />
              Anterior
            </button>
            <span className="min-w-12 text-center text-xs font-bold text-gov-gray-500 dark:text-dark-muted">
              {page}/{pageCount}
            </span>
            <button
              type="button"
              disabled={page >= pageCount}
              onClick={onNextPage}
              className="inline-flex items-center gap-1 rounded-xl border border-gov-gray-200 px-3 py-2 text-xs font-bold disabled:opacity-40 dark:border-dark-border"
            >
              Siguiente
              <ChevronRight size={14} />
            </button>
          </div>
        </>
      )}
    </section>
  );
}
