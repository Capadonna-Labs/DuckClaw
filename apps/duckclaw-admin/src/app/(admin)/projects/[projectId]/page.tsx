'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { Bot, ChevronRight, FolderKanban, PlayCircle } from 'lucide-react';
import { adminService } from '@/services/adminService';
import type { WorkspaceProjectSummary } from '@/services/adminService';

type ProjectDetailResponse = Awaited<ReturnType<typeof adminService.getWorkspaceProject>>;

function fmt(value?: string): string {
  if (!value) return '—';
  const t = Date.parse(value);
  if (Number.isNaN(t)) return value;
  return new Date(t).toLocaleString();
}

export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const [detail, setDetail] = useState<ProjectDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!projectId) return;
    setLoading(true);
    setError(null);
    adminService
      .getWorkspaceProject(projectId)
      .then(setDetail)
      .catch((e) => setError(e instanceof Error ? e.message : 'No se pudo cargar el proyecto'))
      .finally(() => setLoading(false));
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  const project = detail?.project;
  const agents = useMemo(() => detail?.agents ?? project?.agents ?? [], [detail?.agents, project?.agents]);
  const firstAgent = agents[0];

  if (loading) {
    return <p className="text-sm text-gov-gray-500">Cargando proyecto…</p>;
  }

  if (error || !project) {
    return (
      <div className="rounded-2xl border border-red-200 bg-red-50 p-6 text-sm text-red-700 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300">
        {error || 'Proyecto no encontrado'}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <nav className="flex items-center gap-2 text-sm text-gov-gray-500 dark:text-dark-muted">
        <Link href="/projects" className="hover:text-gov-blue-700">
          Proyectos
        </Link>
        <ChevronRight size={14} />
        <span className="font-mono text-gov-gray-900 dark:text-dark-text">{project.project_id}</span>
      </nav>

      <header className="rounded-3xl border border-gov-blue-100 bg-white p-6 dark:border-dark-border dark:bg-dark-surface">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <h1 className="flex items-center gap-2 text-3xl font-black text-gov-gray-900 dark:text-dark-text">
              <FolderKanban size={28} /> {project.name}
            </h1>
            <p className="mt-2 max-w-3xl text-sm text-gov-gray-600 dark:text-dark-muted">
              {project.description || 'Sin descripción.'}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link
              href={`/playground?worker=platform-orchestrator&project=${encodeURIComponent(project.project_id)}`}
              className="inline-flex items-center gap-2 rounded-xl border border-gov-blue-200 px-4 py-2 text-sm font-black text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:text-dark-cyan"
            >
              <PlayCircle size={16} />
              Guiar con Orchestrator
            </Link>
            {firstAgent && (
              <Link
                href={`/playground?worker=${encodeURIComponent(firstAgent.worker_id)}&project=${encodeURIComponent(project.project_id)}`}
                className="inline-flex items-center gap-2 rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-black text-white hover:bg-gov-blue-900"
              >
                <Bot size={16} />
                Probar agente
              </Link>
            )}
          </div>
        </div>
      </header>

      <section className="grid gap-4 lg:grid-cols-3">
        <InfoCard label="Estado" value={project.status} />
        <InfoCard label="Visibilidad" value={project.visibility} />
        <InfoCard label="Agentes" value={String(agents.length)} />
        <InfoCard label="Owner" value={project.owner_email} />
        <InfoCard label="Tenant" value={project.tenant_id} mono />
        <InfoCard label="Actualizado" value={fmt(project.updated_at)} />
      </section>

      <section className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
        <div className="mb-4">
          <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">Contexto del proyecto</h2>
          <p className="text-sm text-gov-gray-500 dark:text-dark-muted">
            Este bloque se inyecta al Playground cuando envías mensajes con `project_id`.
          </p>
        </div>
        <div className="rounded-2xl bg-gov-gray-50 p-4 text-sm dark:bg-dark-bg">
          <p className="font-black text-gov-gray-900 dark:text-dark-text">{project.name}</p>
          <p className="mt-2 text-gov-gray-600 dark:text-dark-muted">{project.description || 'Sin descripción.'}</p>
        </div>
      </section>

      <section className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
        <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">Agentes asignados</h2>
        {agents.length === 0 ? (
          <p className="mt-3 text-sm text-gov-gray-500 dark:text-dark-muted">
            Este proyecto aún no tiene agentes asignados.
          </p>
        ) : (
          <div className="mt-4 grid gap-3">
            {agents.map((agent) => (
              <ProjectAgentCard key={`${agent.worker_uid}-${agent.worker_id}`} project={project} agent={agent} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function InfoCard({ label, value, mono = false }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-2xl border border-gov-blue-100 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
      <p className="text-[10px] font-black uppercase tracking-wider text-gov-gray-500 dark:text-dark-muted">
        {label}
      </p>
      <p className={`mt-1 text-sm font-bold text-gov-gray-900 dark:text-dark-text ${mono ? 'font-mono break-all' : ''}`}>
        {value || '—'}
      </p>
    </div>
  );
}

function ProjectAgentCard({
  project,
  agent,
}: {
  project: WorkspaceProjectSummary;
  agent: NonNullable<WorkspaceProjectSummary['agents']>[number];
}) {
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-gov-blue-50 p-4 dark:border-dark-border md:flex-row md:items-center md:justify-between">
      <div>
        <p className="font-black text-gov-gray-900 dark:text-dark-text">{agent.display_name || agent.worker_id}</p>
        <p className="font-mono text-[11px] text-gov-gray-500 dark:text-dark-muted">{agent.worker_id}</p>
        <p className="mt-1 text-xs text-gov-gray-500 dark:text-dark-muted">Rol: {agent.role || 'member'}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        <Link
          href={`/templates/${encodeURIComponent(agent.worker_id)}?focus=system_prompt.md`}
          className="rounded-xl border border-gov-blue-100 px-3 py-2 text-xs font-bold text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:text-dark-cyan"
        >
          Editar worker
        </Link>
        <Link
          href={`/playground?worker=${encodeURIComponent(agent.worker_id)}&project=${encodeURIComponent(project.project_id)}`}
          className="rounded-xl bg-gov-blue-700 px-3 py-2 text-xs font-bold text-white hover:bg-gov-blue-900"
        >
          Probar en Playground
        </Link>
      </div>
    </div>
  );
}
