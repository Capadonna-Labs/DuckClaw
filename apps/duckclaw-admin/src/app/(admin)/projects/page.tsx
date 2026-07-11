'use client';

import { useCallback, useEffect, useState } from 'react';
import { FolderKanban } from 'lucide-react';
import { ProjectsControlPanel } from '@/components/projects/ProjectsControlPanel';
import { ProjectsGrid } from '@/components/projects/ProjectsGrid';
import ConfirmDangerModal from '@/components/admin/ConfirmDangerModal';
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
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pendingDeleteProject, setPendingDeleteProject] = useState<WorkspaceProjectSummary | null>(null);
  const [deletingProject, setDeletingProject] = useState(false);

  const reload = useCallback(() => {
    setLoading(true);
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
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'))
      .finally(() => setLoading(false));
  }, [query, status, sort, direction, limit, offset]);

  useEffect(() => {
    reload();
  }, [reload]);

  const requestDeleteProject = (project: WorkspaceProjectSummary) => {
    if (!canWrite) return;
    setPendingDeleteProject(project);
  };

  const confirmDeleteProject = async () => {
    if (!canWrite || !pendingDeleteProject) return;
    setError(null);
    setDeletingProject(true);
    try {
      await adminService.deleteWorkspaceProject(pendingDeleteProject.project_id);
      setPendingDeleteProject(null);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo eliminar el proyecto');
    } finally {
      setDeletingProject(false);
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
      <header>
        <h1 className="flex items-center gap-2 text-3xl font-black text-gov-gray-900 dark:text-dark-text">
          <FolderKanban size={28} />
          Proyectos
        </h1>
        <p className="mt-1 text-sm text-gov-gray-600 dark:text-dark-muted">
          Equipos de agentes con contexto compartido para el chat.
        </p>
      </header>

      {error ? (
        <div className="rounded-2xl border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
          {error}
        </div>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-12">
        <div className="lg:col-span-4">
          <ProjectsControlPanel
            canWrite={canWrite}
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
        </div>
        <div className="lg:col-span-8">
          <ProjectsGrid
            projects={projects}
            total={total}
            page={page}
            pageCount={pageCount}
            canWrite={canWrite}
            loading={loading}
            onRefresh={reload}
            onPrevPage={() => setOffset(Math.max(0, offset - limit))}
            onNextPage={() => setOffset(offset + limit)}
            onDelete={requestDeleteProject}
            onDeactivate={(project) => void deactivateProject(project)}
            onReactivate={(project) => void reactivateProject(project)}
          />
        </div>
      </div>

      <ConfirmDangerModal
        isOpen={Boolean(pendingDeleteProject)}
        title="Eliminar proyecto definitivo"
        description="Se eliminará definitivamente de la tabla de proyectos y se quitarán sus asignaciones. No se borran workers, versiones ni templates."
        confirmLabel="Sí, eliminar proyecto"
        isLoading={deletingProject}
        details={
          pendingDeleteProject
            ? [
                { label: 'Proyecto', value: pendingDeleteProject.name },
                { label: 'Project ID', value: pendingDeleteProject.project_id },
                { label: 'Agentes', value: String(pendingDeleteProject.agent_count ?? 0) },
                { label: 'Estado', value: pendingDeleteProject.status },
              ]
            : []
        }
        onCancel={() => !deletingProject && setPendingDeleteProject(null)}
        onConfirm={() => void confirmDeleteProject()}
      />
    </div>
  );
}
