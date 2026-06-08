'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { FolderKanban, Plus } from 'lucide-react';
import { ProjectsCatalogToolbar } from '@/components/projects/ProjectsCatalogToolbar';
import { ProjectsTable } from '@/components/projects/ProjectsTable';
import { adminService } from '@/services/adminService';
import type { WorkspaceProjectSummary, WorkspaceProjectsQuery } from '@/services/adminService';
import { useAuthStore } from '@/store/authStore';

type CatalogSort = NonNullable<WorkspaceProjectsQuery['sort']>;
type CatalogDirection = NonNullable<WorkspaceProjectsQuery['direction']>;
type CatalogStatus = NonNullable<WorkspaceProjectsQuery['status']>;

export default function ProjectsPage() {
  const { usuario } = useAuthStore();
  const canWrite = usuario?.rol === 'admin';
  const [projects, setProjects] = useState<WorkspaceProjectSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [query, setQuery] = useState('');
  const [status, setStatus] = useState<CatalogStatus>('active');
  const [sort, setSort] = useState<CatalogSort>('updated_at');
  const [direction, setDirection] = useState<CatalogDirection>('desc');
  const [limit, setLimit] = useState(25);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    setError(null);
    adminService
      .listWorkspaceProjectsPage({ q: query, status, sort, direction, limit, offset })
      .then((page) => {
        const maxOffset = Math.max(0, Math.floor((page.total - 1) / limit) * limit);
        if (page.projects.length === 0 && page.total > 0 && offset > maxOffset) {
          setOffset(maxOffset);
          return;
        }
        setProjects(page.projects);
        setTotal(page.total);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, [query, status, sort, direction, limit, offset]);

  useEffect(() => {
    reload();
  }, [reload]);

  const deleteProject = async (project: WorkspaceProjectSummary) => {
    if (!canWrite) return;
    const confirmed = window.confirm(
      `Eliminar definitivamente "${project.name}"?\n\nSe eliminará definitivamente de la tabla de proyectos y se quitarán sus asignaciones. No se borran workers, versiones ni templates.`
    );
    if (!confirmed) return;
    setError(null);
    try {
      await adminService.deleteWorkspaceProject(project.project_id);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo eliminar el proyecto');
    }
  };

  const deactivateProject = async (project: WorkspaceProjectSummary) => {
    if (!canWrite) return;
    const confirmed = window.confirm(
      `Desactivar proyecto "${project.name}"?\n\nSaldrá del Playground y del contexto LLM hasta que lo reactives. No se borran datos.`
    );
    if (!confirmed) return;
    setError(null);
    try {
      await adminService.deactivateWorkspaceProject(project.project_id);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo desactivar el proyecto');
    }
  };

  const reactivateProject = async (project: WorkspaceProjectSummary) => {
    if (!canWrite) return;
    setError(null);
    try {
      await adminService.reactivateWorkspaceProject(project.project_id);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo activar el proyecto');
    }
  };

  const page = Math.floor(offset / limit) + 1;
  const pageCount = Math.max(1, Math.ceil(total / limit));

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div>
          <h1 className="flex items-center gap-2 text-3xl font-black text-gov-gray-900 dark:text-dark-text">
            <FolderKanban size={28} /> Proyectos
          </h1>
        </div>
        {canWrite && (
          <Link
            href="/projects/orchestrator"
            className="inline-flex items-center gap-2 rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-bold text-white hover:bg-gov-blue-900"
          >
            <Plus size={16} /> Nuevo proyecto
          </Link>
        )}
      </header>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <ProjectsCatalogToolbar
        query={query}
        status={status}
        sort={sort}
        direction={direction}
        limit={limit}
        onQueryChange={(value) => {
          setQuery(value);
          setOffset(0);
        }}
        onStatusChange={(value) => {
          setStatus(value);
          setOffset(0);
        }}
        onSortChange={(value) => {
          setSort(value);
          setOffset(0);
        }}
        onDirectionChange={(value) => {
          setDirection(value);
          setOffset(0);
        }}
        onLimitChange={(value) => {
          setLimit(value);
          setOffset(0);
        }}
      />

      <ProjectsTable
        projects={projects}
        canWrite={canWrite}
        onDelete={(project) => void deleteProject(project)}
        onDeactivate={(project) => void deactivateProject(project)}
        onReactivate={(project) => void reactivateProject(project)}
      />

      <div className="flex items-center justify-between rounded-2xl border border-gov-blue-100 bg-white px-4 py-3 text-sm text-gov-gray-700 dark:border-dark-border dark:bg-dark-surface dark:text-dark-text">
        <span>
          Página {page} de {pageCount} · {total} proyectos
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - limit))}
            className="rounded-xl border border-gov-blue-100 px-3 py-1 font-bold disabled:opacity-50 dark:border-dark-border"
          >
            Anterior
          </button>
          <button
            type="button"
            disabled={offset + limit >= total}
            onClick={() => setOffset(offset + limit)}
            className="rounded-xl border border-gov-blue-100 px-3 py-1 font-bold disabled:opacity-50 dark:border-dark-border"
          >
            Siguiente
          </button>
        </div>
      </div>
    </div>
  );
}
