'use client';

import Link from 'next/link';
import { Eye, Power, RotateCcw, Trash2 } from 'lucide-react';
import type { WorkspaceProjectSummary } from '@/services/adminService';

export type ProjectsTableProps = {
  projects: WorkspaceProjectSummary[];
  canWrite: boolean;
  onDelete: (project: WorkspaceProjectSummary) => void;
  onDeactivate: (project: WorkspaceProjectSummary) => void;
  onReactivate: (project: WorkspaceProjectSummary) => void;
};

export function ProjectsTable({
  projects,
  canWrite,
  onDelete,
  onDeactivate,
  onReactivate,
}: ProjectsTableProps) {
  if (projects.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-gov-blue-200 bg-white p-8 text-center dark:border-dark-border dark:bg-dark-surface">
        <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">Aún no hay proyectos</h2>
        <p className="mx-auto mt-2 max-w-md text-sm text-gov-gray-500 dark:text-dark-muted">
          Crea el primer proyecto con el Orchestrator para guardar contexto DB-first y agentes asignados.
        </p>
        <Link
          href="/projects/orchestrator"
          className="mt-4 inline-flex rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-black text-white hover:bg-gov-blue-900"
        >
          Crear primer proyecto
        </Link>
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-2xl border border-gov-blue-100 bg-white dark:border-dark-border dark:bg-dark-surface">
      <table className="min-w-[820px] w-full text-sm">
        <thead className="bg-gov-gray-50 text-left text-[11px] uppercase tracking-wide text-gov-gray-500 dark:bg-dark-bg dark:text-dark-muted">
          <tr>
            <th className="px-4 py-3">Proyecto</th>
            <th className="px-4 py-3">Estado</th>
            <th className="px-4 py-3">Agentes</th>
            <th className="min-w-[18rem] px-4 py-3 text-right">Acciones</th>
          </tr>
        </thead>
        <tbody>
          {projects.map((project) => (
            <tr
              key={project.project_id}
              className="border-t border-gov-blue-50 hover:bg-gov-gray-50/70 dark:border-dark-border dark:hover:bg-dark-bg"
            >
              <td className="px-4 py-3">
                <p className="font-black text-gov-gray-900 dark:text-dark-text">{project.name}</p>
                <p className="mt-0.5 font-mono text-[11px] text-gov-gray-500 dark:text-dark-muted">
                  {project.project_id}
                </p>
                {project.description && (
                  <p className="mt-1 max-w-xl truncate text-xs text-gov-gray-500 dark:text-dark-muted">
                    {project.description}
                  </p>
                )}
              </td>
              <td className="px-4 py-3">
                <span className="rounded-full bg-gov-blue-50 px-2.5 py-1 text-[11px] font-black uppercase tracking-wide text-gov-blue-800 dark:bg-dark-bg dark:text-dark-cyan">
                  {project.status}
                </span>
              </td>
              <td className="px-4 py-3 text-gov-gray-700 dark:text-dark-text">{project.agent_count ?? 0}</td>
              <td className="px-4 py-3">
                <div className="flex flex-wrap justify-end gap-2 whitespace-nowrap">
                  <Link
                    href={`/projects/${encodeURIComponent(project.project_id)}`}
                    className="inline-flex items-center gap-1 rounded-full border border-gov-blue-200 px-3 py-1 text-[11px] font-black text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:text-dark-cyan dark:hover:bg-dark-bg"
                    aria-label={`Ver proyecto ${project.name}`}
                  >
                    <Eye size={12} />
                    Ver
                  </Link>
                  {project.status !== 'inactive' && (
                    <Link
                      href={`/playground?worker=platform-orchestrator&project=${encodeURIComponent(project.project_id)}`}
                      className="rounded-full border border-gov-blue-200 px-3 py-1 text-[11px] font-black text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:text-dark-cyan dark:hover:bg-dark-bg"
                    >
                      Guiar
                    </Link>
                  )}
                  {canWrite && (
                    <>
                      {project.status === 'inactive' ? (
                        <button
                          type="button"
                          onClick={() => onReactivate(project)}
                          className="inline-flex items-center gap-1 rounded-full border border-gov-blue-200 px-3 py-1 text-[11px] font-black text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:text-dark-cyan dark:hover:bg-dark-bg"
                          aria-label={`Activar proyecto ${project.name}`}
                        >
                          <RotateCcw size={12} />
                          Activar
                        </button>
                      ) : (
                        <button
                          type="button"
                          onClick={() => onDeactivate(project)}
                          className="inline-flex items-center gap-1 rounded-full border border-amber-200 px-3 py-1 text-[11px] font-black text-amber-700 hover:bg-amber-50 dark:border-amber-900/60 dark:text-amber-300 dark:hover:bg-amber-950/30"
                          aria-label={`Desactivar proyecto ${project.name}`}
                        >
                          <Power size={12} />
                          Desactivar
                        </button>
                      )}
                      <button
                        type="button"
                        onClick={() => onDelete(project)}
                        className="inline-flex items-center gap-1 rounded-full border border-red-200 px-3 py-1 text-[11px] font-black text-red-700 hover:bg-red-50 dark:border-red-900/60 dark:text-red-300 dark:hover:bg-red-950/30"
                        aria-label={`Eliminar definitivamente proyecto ${project.name}`}
                      >
                        <Trash2 size={12} />
                        Eliminar definitivo
                      </button>
                    </>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
