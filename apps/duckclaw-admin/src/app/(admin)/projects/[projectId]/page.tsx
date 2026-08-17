'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import { Bot, ChevronRight, Database, PlayCircle, RefreshCw } from 'lucide-react';
import { adminService } from '@/services/adminService';
import type { KnowledgeSource, WorkspaceProjectSummary } from '@/services/adminService';
import { KnowledgeStatusBadge } from '@/components/knowledge/KnowledgeStatusBadge';
import {
  knowledgeSourcePrimaryLabel,
  knowledgeSourceSecondaryLine,
} from '@/components/knowledge/knowledgeSourceLabel';
import { ProjectAgentsSection } from '@/components/projects/ProjectAgentsSection';
import {
  ProjectContextEditor,
  ProjectNameEditor,
} from '@/components/projects/ProjectInlineEditors';
import { useAuthStore } from '@/store/authStore';
import { isAdminRole } from '@/lib/roles';

type ProjectDetailResponse = Awaited<ReturnType<typeof adminService.getWorkspaceProject>>;

function fmt(value?: string): string {
  if (!value) return '—';
  const t = Date.parse(value);
  if (Number.isNaN(t)) return value;
  return new Date(t).toLocaleString();
}

export default function ProjectDetailPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const { usuario } = useAuthStore();
  const canWrite = isAdminRole(usuario?.rol);
  const [detail, setDetail] = useState<ProjectDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [knowledgeSources, setKnowledgeSources] = useState<KnowledgeSource[]>([]);
  const [knowledgeLoading, setKnowledgeLoading] = useState(false);
  const [knowledgeError, setKnowledgeError] = useState<string | null>(null);

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

  const loadKnowledge = useCallback(() => {
    if (!projectId) return;
    setKnowledgeLoading(true);
    setKnowledgeError(null);
    adminService
      .listKnowledgeSources({ project_id: projectId })
      .then(setKnowledgeSources)
      .catch((e) => setKnowledgeError(e instanceof Error ? e.message : 'No se pudo cargar conocimiento RAG'))
      .finally(() => setKnowledgeLoading(false));
  }, [projectId]);

  useEffect(() => {
    loadKnowledge();
  }, [loadKnowledge]);

  const applyProjectPatch = useCallback((next: WorkspaceProjectSummary) => {
    setDetail((prev) =>
      prev
        ? {
            ...prev,
            project: { ...prev.project, ...next },
          }
        : prev
    );
  }, []);

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
            <ProjectNameEditor project={project} canEdit={canWrite} onSaved={applyProjectPatch} />
            <p className="mt-2 max-w-3xl text-sm text-gov-gray-600 dark:text-dark-muted">
              {project.description || 'Sin descripción.'}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link
              href={`/playground?project=${encodeURIComponent(project.project_id)}`}
              className="inline-flex items-center gap-2 rounded-xl border border-gov-blue-200 px-4 py-2 text-sm font-black text-gov-blue-800 hover:bg-gov-blue-50 dark:border-dark-border dark:text-dark-cyan"
            >
              <PlayCircle size={16} />
              Abrir playground
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

      <ProjectContextEditor project={project} canEdit={canWrite} onSaved={applyProjectPatch} />

      <section className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h2 className="flex items-center gap-2 text-lg font-black text-gov-gray-900 dark:text-dark-text">
              <Database size={18} />
              Conocimiento RAG
            </h2>
            <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
              Resumen de fuentes DB-first asociadas a este proyecto.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link
              href={`/knowledge?project=${encodeURIComponent(project.project_id)}`}
              className="rounded-xl bg-gov-blue-700 px-3 py-2 text-xs font-black text-white hover:bg-gov-blue-900"
            >
              Gestionar RAG
            </Link>
            <button
              type="button"
              onClick={loadKnowledge}
              disabled={knowledgeLoading}
              className="inline-flex items-center gap-2 rounded-xl border border-gov-blue-100 px-3 py-2 text-xs font-bold text-gov-blue-800 disabled:opacity-50 dark:border-dark-border dark:text-dark-cyan"
            >
              <RefreshCw size={14} />
              Refrescar
            </button>
          </div>
        </div>

        {knowledgeError && <p className="mt-3 text-sm text-red-600">{knowledgeError}</p>}

        {knowledgeLoading ? (
          <p className="mt-4 text-sm text-gov-gray-500 dark:text-dark-muted">Cargando fuentes RAG…</p>
        ) : knowledgeSources.length === 0 ? (
          <p className="mt-4 rounded-2xl border border-dashed border-gov-blue-100 p-4 text-sm text-gov-gray-500 dark:border-dark-border dark:text-dark-muted">
            Sin fuentes RAG asociadas todavía.
          </p>
        ) : (
          <div className="mt-4 grid gap-3">
            {knowledgeSources.map((source) => (
              <KnowledgeSourceCard key={source.source_id} source={source} />
            ))}
          </div>
        )}
      </section>

      <ProjectAgentsSection
        project={project}
        agents={agents}
        canWrite={canWrite}
        onChanged={load}
      />
    </div>
  );
}

function KnowledgeSourceCard({
  source,
}: {
  source: KnowledgeSource;
}) {
  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-gov-blue-50 p-4 dark:border-dark-border md:flex-row md:items-center md:justify-between">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <p className="font-black text-gov-gray-900 dark:text-dark-text">
            {knowledgeSourcePrimaryLabel(source)}
          </p>
          <KnowledgeStatusBadge source={source} />
        </div>
        {knowledgeSourceSecondaryLine(source) && (
          <p className="mt-1 truncate font-mono text-[11px] text-gov-gray-500 dark:text-dark-muted">
            {knowledgeSourceSecondaryLine(source)}
          </p>
        )}
        <p className="mt-2 text-xs text-gov-gray-500 dark:text-dark-muted">
          {source.document_count} documento{source.document_count === 1 ? '' : 's'} ·{' '}
          {source.chunk_count} fragmento{source.chunk_count === 1 ? '' : 's'}
        </p>
      </div>
      <span className="rounded-full border border-gov-blue-100 px-3 py-1 text-[11px] font-black uppercase tracking-wider text-gov-blue-700 dark:border-dark-border dark:text-dark-cyan">
        {source.source_kind || 'file'}
      </span>
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
