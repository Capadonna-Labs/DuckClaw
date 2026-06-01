'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { adminService } from '@/services/adminService';
import { useAuthStore } from '@/store/authStore';
import { FolderKanban, Plus, Trash2 } from 'lucide-react';
import type { TemplateSummary } from '@/types/admin';

type WorkspaceProject = Awaited<ReturnType<typeof adminService.listWorkspaceProjects>>[number];
type WorkspaceProjectAgent = Awaited<ReturnType<typeof adminService.listWorkspaceProjectAgents>>[number];

export default function ProjectsPage() {
  const { usuario } = useAuthStore();
  const canWrite = usuario?.rol === 'admin';
  const [workspaceProjects, setWorkspaceProjects] = useState<WorkspaceProject[]>([]);
  const [workspaceAgents, setWorkspaceAgents] = useState<Record<string, WorkspaceProjectAgent[]>>({});
  const [visibleWorkers, setVisibleWorkers] = useState<TemplateSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectDescription, setNewProjectDescription] = useState('');
  const [selectedWorkers, setSelectedWorkers] = useState<Record<string, string>>({});

  const reload = useCallback(() => {
    async function loadAll() {
      const [dbProjects, templates] = await Promise.all([
        adminService.listWorkspaceProjects(),
        adminService.listTemplates(),
      ]);
      setWorkspaceProjects(dbProjects);
      setVisibleWorkers(templates.filter((t) => t.source === 'catalog' && t.worker_uid));
      const pairs = await Promise.all(
        dbProjects.map(async (project) => [
          project.project_id,
          await adminService.listWorkspaceProjectAgents(project.project_id),
        ] as const)
      );
      setWorkspaceAgents(Object.fromEntries(pairs));
    }
    loadAll().catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const createDbProject = async () => {
    if (!canWrite || !newProjectName.trim()) return;
    setError(null);
    try {
      await adminService.createWorkspaceProject({
        name: newProjectName.trim(),
        description: newProjectDescription.trim(),
      });
      setNewProjectName('');
      setNewProjectDescription('');
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo crear el proyecto');
    }
  };

  const assignDbWorker = async (projectId: string) => {
    const workerId = selectedWorkers[projectId];
    if (!canWrite || !workerId) return;
    setError(null);
    try {
      await adminService.assignWorkspaceProjectAgent(projectId, {
        worker_id: workerId,
        role: 'member',
        sort_order: (workspaceAgents[projectId]?.length ?? 0) * 10,
      });
      setSelectedWorkers((prev) => ({ ...prev, [projectId]: '' }));
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo asignar el agente');
    }
  };

  const removeDbWorker = async (projectId: string, workerId: string) => {
    if (!canWrite) return;
    setError(null);
    try {
      await adminService.removeWorkspaceProjectAgent(projectId, workerId);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo quitar el agente');
    }
  };

  return (
    <div className="space-y-6">
      <header className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black text-gov-gray-900 dark:text-dark-text flex items-center gap-2">
            <FolderKanban size={28} /> Proyectos
          </h1>
          <p className="text-sm text-gov-gray-500 dark:text-dark-muted mt-1">
            Organiza tus agentes por proyecto.
          </p>
        </div>
        {canWrite && (
          <Link
            href="/projects/new"
            className="inline-flex items-center gap-2 px-4 py-2 bg-gov-blue-700 text-white text-sm font-bold rounded-xl"
          >
            <Plus size={16} /> Nuevo proyecto o agente
          </Link>
        )}
      </header>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      <section className="rounded-2xl border border-gov-blue-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gov-blue-700 dark:text-dark-cyan">
              Proyectos
            </p>
            <h2 className="mt-1 text-xl font-black dark:text-dark-text">Proyectos con agentes asignados</h2>
            <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
              Elige qué agentes pertenecen a cada proyecto.
            </p>
          </div>
          {canWrite && (
            <div className="grid gap-2 md:w-[420px]">
              <input
                value={newProjectName}
                onChange={(e) => setNewProjectName(e.target.value)}
                placeholder="Nombre del proyecto"
                className="rounded-xl border px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
              />
              <div className="flex gap-2">
                <input
                  value={newProjectDescription}
                  onChange={(e) => setNewProjectDescription(e.target.value)}
                  placeholder="Descripción opcional"
                  className="min-w-0 flex-1 rounded-xl border px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
                />
                <button
                  type="button"
                  onClick={() => void createDbProject()}
                  className="inline-flex items-center gap-2 rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-bold text-white"
                >
                  <Plus size={16} /> Crear
                </button>
              </div>
            </div>
          )}
        </div>

        {workspaceProjects.length === 0 ? (
          <p className="mt-4 rounded-xl bg-gov-gray-50 px-4 py-3 text-sm text-gov-gray-500 dark:bg-dark-bg dark:text-dark-muted">
            Aún no hay proyectos para tu usuario.
          </p>
        ) : (
          <div className="mt-5 grid gap-4">
            {workspaceProjects.map((project) => (
              <article
                key={project.project_id}
                className="rounded-2xl border bg-gov-gray-50/80 p-4 dark:border-dark-border dark:bg-dark-bg"
              >
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div>
                    <h3 className="font-black dark:text-dark-text">{project.name}</h3>
                    <p className="mt-0.5 font-mono text-[11px] text-gov-gray-500">{project.project_id}</p>
                    {project.description && (
                      <p className="mt-2 text-sm text-gov-gray-600 dark:text-dark-muted">{project.description}</p>
                    )}
                  </div>
                  <span className="rounded-full bg-gov-cyan-100 px-3 py-1 text-[11px] font-black text-gov-blue-800">
                    {workspaceAgents[project.project_id]?.length ?? project.agent_count ?? 0} agentes
                  </span>
                </div>

                <div className="mt-3 flex flex-wrap gap-2">
                  {(workspaceAgents[project.project_id] ?? []).map((agent) => (
                    <span
                      key={agent.worker_uid}
                      className="inline-flex items-center gap-2 rounded-xl bg-white px-3 py-1.5 text-xs font-mono dark:bg-dark-surface"
                    >
                      <Link href={`/templates/${agent.worker_id}`} className="hover:text-gov-blue-700">
                        {agent.worker_id}
                      </Link>
                      <small className="font-sans text-gov-gray-400">{agent.role}</small>
                      {canWrite && (
                        <button
                          type="button"
                          onClick={() => void removeDbWorker(project.project_id, agent.worker_id)}
                          className="text-red-600"
                          aria-label={`Quitar ${agent.worker_id}`}
                        >
                          <Trash2 size={12} />
                        </button>
                      )}
                    </span>
                  ))}
                </div>

                {canWrite && (
                  <div className="mt-4 flex flex-col gap-2 sm:flex-row">
                    <select
                      value={selectedWorkers[project.project_id] ?? ''}
                      onChange={(e) =>
                        setSelectedWorkers((prev) => ({ ...prev, [project.project_id]: e.target.value }))
                      }
                      className="min-w-0 flex-1 rounded-xl border px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-surface"
                    >
                      <option value="">Selecciona worker del catálogo</option>
                      {visibleWorkers.map((worker) => (
                        <option key={worker.id} value={worker.id}>
                          {worker.name || worker.id}
                        </option>
                      ))}
                    </select>
                    <button
                      type="button"
                      onClick={() => void assignDbWorker(project.project_id)}
                      className="rounded-xl border px-4 py-2 text-sm font-bold hover:border-gov-blue-500 dark:border-dark-border"
                    >
                      Asignar agente
                    </button>
                  </div>
                )}
              </article>
            ))}
          </div>
        )}
      </section>

    </div>
  );
}
