'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { adminService } from '@/services/adminService';
import type { OrchestratorDraft } from '@/services/adminService';
import { useAuthStore } from '@/store/authStore';
import { FolderKanban, Plus, Sparkles, Trash2 } from 'lucide-react';
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
  const [orchestratorPrompt, setOrchestratorPrompt] = useState('');
  const [orchestratorDraft, setOrchestratorDraft] = useState<OrchestratorDraft | null>(null);
  const [orchestratorBusy, setOrchestratorBusy] = useState(false);

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

  const createGuidedDraft = async () => {
    const prompt = orchestratorPrompt.trim();
    if (!canWrite || prompt.length < 10) return;
    setError(null);
    setOrchestratorBusy(true);
    try {
      const draft = await adminService.createOrchestratorDraft({ prompt });
      setOrchestratorDraft(draft);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo generar el borrador guiado');
    } finally {
      setOrchestratorBusy(false);
    }
  };

  const confirmGuidedDraft = async () => {
    if (!canWrite || !orchestratorDraft) return;
    const confirmed = window.confirm(
      `Crear proyecto "${orchestratorDraft.project.name}" con ${orchestratorDraft.workers.length} agente(s)?`
    );
    if (!confirmed) return;
    setError(null);
    setOrchestratorBusy(true);
    try {
      await adminService.confirmOrchestratorDraft(orchestratorDraft);
      setOrchestratorPrompt('');
      setOrchestratorDraft(null);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo confirmar el borrador guiado');
    } finally {
      setOrchestratorBusy(false);
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

  const deleteDbProject = async (project: WorkspaceProject) => {
    if (!canWrite) return;
    const confirmed = window.confirm(
      `Eliminar proyecto "${project.name}"?\n\nSe ocultará el proyecto y se quitarán sus agentes asignados. No se borran workers, versiones ni templates.`
    );
    if (!confirmed) return;
    setError(null);
    try {
      await adminService.deleteWorkspaceProject(project.project_id);
      setWorkspaceAgents((prev) => {
        const next = { ...prev };
        delete next[project.project_id];
        return next;
      });
      setSelectedWorkers((prev) => {
        const next = { ...prev };
        delete next[project.project_id];
        return next;
      });
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo eliminar el proyecto');
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
            Agrupa tus agentes por cliente, flujo o iniciativa.
          </p>
        </div>
        {canWrite && (
          <a
            href="#platform-orchestrator"
            className="inline-flex items-center gap-2 px-4 py-2 bg-gov-blue-700 text-white text-sm font-bold rounded-xl"
          >
            <Plus size={16} /> Crear con Orchestrator
          </a>
        )}
      </header>

      {error && <p className="text-red-600 text-sm">{error}</p>}

      {canWrite && (
        <section id="platform-orchestrator" className="overflow-hidden rounded-3xl border border-gov-blue-100 bg-gradient-to-br from-white via-gov-cyan-50 to-gov-gray-50 p-5 shadow-sm dark:border-dark-border dark:from-dark-surface dark:via-dark-bg dark:to-slate-950">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-2xl">
              <p className="inline-flex items-center gap-2 rounded-full bg-gov-blue-700 px-3 py-1 text-[10px] font-black uppercase tracking-[0.18em] text-white">
                <Sparkles size={12} /> Platform Orchestrator
              </p>
              <h2 className="mt-3 text-2xl font-black text-gov-gray-900 dark:text-dark-text">
                Crea tu proyecto con preguntas guiadas
              </h2>
              <p className="mt-2 text-sm text-gov-gray-600 dark:text-dark-muted">
                Describe objetivo, datos y resultado esperado. El orquestador prepara un borrador
                DB-first de proyecto, agente, contexto compartido y skills sugeridas antes de crear nada.
              </p>
            </div>
            <Link
              href="/playground?worker_id=platform-orchestrator"
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-gov-blue-200 bg-white px-4 py-2 text-sm font-black text-gov-blue-800 hover:border-gov-blue-500 dark:border-dark-border dark:bg-dark-bg dark:text-dark-cyan"
            >
              Abrir chat del Orchestrator
            </Link>
          </div>

          <div className="mt-5 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(320px,420px)]">
            <div className="space-y-3">
              <textarea
                value={orchestratorPrompt}
                onChange={(e) => setOrchestratorPrompt(e.target.value)}
                placeholder="Ej: Quiero un proyecto para soporte comercial que consulte clientes CRM, clasifique casos y genere respuestas aprobables por humano..."
                rows={6}
                className="w-full rounded-2xl border border-gov-blue-100 bg-white px-4 py-3 text-sm outline-none focus:border-gov-blue-500 dark:border-dark-border dark:bg-dark-bg dark:text-dark-text"
              />
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  onClick={() => void createGuidedDraft()}
                  disabled={orchestratorBusy || orchestratorPrompt.trim().length < 10}
                  className="inline-flex items-center gap-2 rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-black text-white disabled:opacity-50"
                >
                  <Sparkles size={16} /> Generar borrador
                </button>
                {orchestratorDraft && (
                  <button
                    type="button"
                    onClick={() => setOrchestratorDraft(null)}
                    disabled={orchestratorBusy}
                    className="rounded-xl border px-4 py-2 text-sm font-bold dark:border-dark-border"
                  >
                    Descartar
                  </button>
                )}
              </div>
            </div>

            <aside className="rounded-2xl border border-gov-blue-100 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
              {orchestratorDraft ? (
                <div className="space-y-3">
                  <div>
                    <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gov-blue-700">
                      Borrador revisable
                    </p>
                    <h3 className="mt-1 font-black dark:text-dark-text">{orchestratorDraft.project.name}</h3>
                    <p className="mt-1 text-xs text-gov-gray-500 dark:text-dark-muted">
                      {orchestratorDraft.project.description}
                    </p>
                  </div>
                  <div className="space-y-1">
                    {orchestratorDraft.workers.map((worker) => (
                      <div key={worker.worker_id} className="rounded-xl bg-gov-gray-50 px-3 py-2 text-xs dark:bg-dark-bg">
                        <strong>{worker.display_name}</strong>
                        <span className="ml-2 font-mono text-gov-gray-500">{worker.worker_id}</span>
                      </div>
                    ))}
                  </div>
                  {orchestratorDraft.suggested_skills.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {orchestratorDraft.suggested_skills.map((skill) => (
                        <span
                          key={skill.name}
                          className={`rounded-full px-2 py-1 text-[11px] font-bold ${
                            skill.available
                              ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200'
                              : 'bg-amber-100 text-amber-800 dark:bg-amber-950/40 dark:text-amber-200'
                          }`}
                          title={skill.reason}
                        >
                          {skill.name}
                        </span>
                      ))}
                    </div>
                  )}
                  <button
                    type="button"
                    onClick={() => void confirmGuidedDraft()}
                    disabled={orchestratorBusy}
                    className="w-full rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-black text-white disabled:opacity-50"
                  >
                    Confirmar y crear DB-first
                  </button>
                </div>
              ) : (
                <p className="text-sm text-gov-gray-500 dark:text-dark-muted">
                  El preview aparecerá aquí. Nada se guarda hasta confirmar explícitamente.
                </p>
              )}
            </aside>
          </div>
        </section>
      )}

      <section className="rounded-2xl border border-gov-blue-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface">
        <div className="flex flex-col gap-3 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="text-[10px] font-black uppercase tracking-[0.18em] text-gov-blue-700 dark:text-dark-cyan">
              Catálogo DB-first
            </p>
            <h2 className="mt-1 text-xl font-black dark:text-dark-text">Proyectos con agentes asignados</h2>
            <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
              Elige qué agentes pertenecen a cada proyecto. La asignación se guarda en DuckDB y
              afecta el filtro de agentes del Playground.
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
                  <div className="flex flex-wrap items-center justify-end gap-2">
                    <span className="rounded-full bg-gov-cyan-100 px-3 py-1 text-[11px] font-black text-gov-blue-800">
                      {workspaceAgents[project.project_id]?.length ?? project.agent_count ?? 0} agentes
                    </span>
                    {canWrite && (
                      <button
                        type="button"
                        onClick={() => void deleteDbProject(project)}
                        className="inline-flex items-center gap-1 rounded-full border border-red-200 bg-red-50 px-3 py-1 text-[11px] font-black text-red-700 hover:border-red-300 hover:bg-red-100 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300"
                        aria-label={`Eliminar proyecto ${project.name}`}
                      >
                        <Trash2 size={12} /> Eliminar proyecto
                      </button>
                    )}
                  </div>
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
                      <option value="">Selecciona un agente disponible</option>
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
                {canWrite && visibleWorkers.length === 0 && (
                  <p className="mt-2 rounded-xl bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
                    No hay agentes asignables en tu catálogo DB-first. Importa o crea un agente
                    primero; los templates legacy de archivo no se asignan a proyectos.
                  </p>
                )}
              </article>
            ))}
          </div>
        )}
      </section>

    </div>
  );
}
