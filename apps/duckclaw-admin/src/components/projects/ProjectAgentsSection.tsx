'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { Bot, Plus, Trash2 } from 'lucide-react';
import { adminService } from '@/services/adminService';
import type { TemplateSummary, WorkspaceProjectSummary } from '@/services/adminService';

type ProjectAgent = NonNullable<WorkspaceProjectSummary['agents']>[number];

type ProjectAgentsSectionProps = {
  project: WorkspaceProjectSummary;
  agents: ProjectAgent[];
  canWrite: boolean;
  onChanged: () => void;
};

export function ProjectAgentsSection({
  project,
  agents,
  canWrite,
  onChanged,
}: ProjectAgentsSectionProps) {
  const [catalogWorkers, setCatalogWorkers] = useState<TemplateSummary[]>([]);
  const [selectedWorkerId, setSelectedWorkerId] = useState('');
  const [loadingCatalog, setLoadingCatalog] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const assignedIds = useMemo(
    () => new Set(agents.map((agent) => agent.worker_id)),
    [agents]
  );

  const availableWorkers = useMemo(
    () =>
      catalogWorkers.filter(
        (worker) =>
          worker.id &&
          worker.active !== false &&
          worker.status !== 'inactive' &&
          !assignedIds.has(worker.id)
      ),
    [assignedIds, catalogWorkers]
  );

  const loadCatalog = useCallback(() => {
    setLoadingCatalog(true);
    adminService
      .listTemplates()
      .then(setCatalogWorkers)
      .catch((e) => setError(e instanceof Error ? e.message : 'No se pudo cargar workers'))
      .finally(() => setLoadingCatalog(false));
  }, []);

  useEffect(() => {
    if (!canWrite) return;
    loadCatalog();
  }, [canWrite, loadCatalog]);

  useEffect(() => {
    if (!selectedWorkerId && availableWorkers.length > 0) {
      setSelectedWorkerId(availableWorkers[0].id);
    }
    if (selectedWorkerId && !availableWorkers.some((worker) => worker.id === selectedWorkerId)) {
      setSelectedWorkerId(availableWorkers[0]?.id ?? '');
    }
  }, [availableWorkers, selectedWorkerId]);

  const assignWorker = async () => {
    if (!selectedWorkerId || busy) return;
    setBusy(true);
    setError(null);
    try {
      await adminService.assignWorkspaceProjectAgent(project.project_id, {
        worker_id: selectedWorkerId,
        role: 'member',
      });
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo asignar el worker');
    } finally {
      setBusy(false);
    }
  };

  const removeWorker = async (workerId: string) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await adminService.removeWorkspaceProjectAgent(project.project_id, workerId);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo quitar el worker');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-3xl border border-gov-blue-100 bg-white p-5 dark:border-dark-border dark:bg-dark-surface">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">Agentes asignados</h2>
          <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
            Workers que pueden usarse en Playground con este proyecto.
          </p>
        </div>
        {canWrite && (
          <div className="flex w-full flex-col gap-2 sm:flex-row sm:items-center md:max-w-xl">
            <select
              value={selectedWorkerId}
              onChange={(e) => setSelectedWorkerId(e.target.value)}
              disabled={busy || loadingCatalog || availableWorkers.length === 0}
              className="min-w-0 flex-1 rounded-xl border border-gov-blue-100 px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
              aria-label="Worker a asignar"
            >
              {availableWorkers.length === 0 ? (
                <option value="">
                  {loadingCatalog ? 'Cargando workers…' : 'Sin workers disponibles'}
                </option>
              ) : (
                availableWorkers.map((worker) => (
                  <option key={worker.id} value={worker.id}>
                    {(worker.name || worker.id).trim()} ({worker.id})
                  </option>
                ))
              )}
            </select>
            <button
              type="button"
              onClick={() => void assignWorker()}
              disabled={busy || !selectedWorkerId}
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-black text-white hover:bg-gov-blue-900 disabled:opacity-50"
            >
              <Plus size={16} />
              Asignar worker
            </button>
          </div>
        )}
      </div>

      {error && <p className="mt-3 text-sm text-red-600 dark:text-red-300">{error}</p>}

      {agents.length === 0 ? (
        <p className="mt-4 rounded-2xl border border-dashed border-gov-blue-100 p-4 text-sm text-gov-gray-500 dark:border-dark-border dark:text-dark-muted">
          Este proyecto aún no tiene agentes asignados.
        </p>
      ) : (
        <div className="mt-4 grid gap-3">
          {agents.map((agent) => (
            <div
              key={`${agent.worker_uid}-${agent.worker_id}`}
              className="flex flex-col gap-3 rounded-2xl border border-gov-blue-50 p-4 dark:border-dark-border md:flex-row md:items-center md:justify-between"
            >
              <div className="flex min-w-0 items-start gap-3">
                <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gov-blue-50 text-gov-blue-700 dark:bg-dark-bg dark:text-dark-cyan">
                  <Bot size={18} />
                </div>
                <div className="min-w-0">
                  <p className="font-black text-gov-gray-900 dark:text-dark-text">
                    {agent.display_name || agent.worker_id}
                  </p>
                  <p className="font-mono text-[11px] text-gov-gray-500 dark:text-dark-muted">
                    {agent.worker_id}
                  </p>
                  <p className="mt-1 text-xs text-gov-gray-500 dark:text-dark-muted">
                    Rol: {agent.role || 'member'}
                  </p>
                </div>
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
                {canWrite && (
                  <button
                    type="button"
                    onClick={() => void removeWorker(agent.worker_id)}
                    disabled={busy}
                    className="inline-flex items-center gap-1 rounded-xl border border-red-200 px-3 py-2 text-xs font-bold text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-900/50 dark:text-red-300"
                  >
                    <Trash2 size={14} />
                    Quitar
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
