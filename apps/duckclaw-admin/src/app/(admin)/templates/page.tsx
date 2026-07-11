'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { adminService } from '@/services/adminService';
import type { TemplateSummary } from '@/types/admin';
import EmptyState from '@/components/shared/EmptyState';
import { PageShell } from '@/components/admin/PageShell';
import { useAuthStore } from '@/store/authStore';
import ConfirmDangerModal from '@/components/admin/ConfirmDangerModal';
import { CreateAgentDialog } from '@/components/templates/CreateAgentDialog';
import { isAdminRole } from '@/lib/roles';
import { paginateItems } from '@/lib/pagination';
import { agentCardSubtitle, agentMetadata, agentWorkerIcon } from '@/lib/agentCards';
import { filterVisibleTemplates } from '@/lib/templateVisibility';
import { ChevronLeft, ChevronRight, Plus, Power, Trash2 } from 'lucide-react';

const AGENTS_PAGE_SIZE = 8;

export default function TemplatesPage() {
  const { usuario } = useAuthStore();
  const isAdmin = isAdminRole(usuario?.rol);
  const canWrite = isAdmin;
  const [items, setItems] = useState<TemplateSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [pendingDeactivate, setPendingDeactivate] = useState<TemplateSummary | null>(null);
  const [pendingHardDelete, setPendingHardDelete] = useState<TemplateSummary | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [page, setPage] = useState(1);
  const [createOpen, setCreateOpen] = useState(false);

  const reload = useCallback(() => {
    adminService
      .listTemplates({ include_inactive: false })
      .then((nextItems) => {
        setItems(filterVisibleTemplates(nextItems));
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const confirmDeactivate = async () => {
    if (!pendingDeactivate || !canWrite) return;
    setDeleting(true);
    setError(null);
    try {
      await adminService.deactivateTemplate(pendingDeactivate.id);
      setPendingDeactivate(null);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo desactivar');
    } finally {
      setDeleting(false);
    }
  };

  const confirmHardDelete = async () => {
    if (!pendingHardDelete || !canWrite) return;
    setDeleting(true);
    setError(null);
    try {
      await adminService.hardDeleteTemplate(pendingHardDelete.id);
      setPendingHardDelete(null);
      reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo eliminar definitivamente');
    } finally {
      setDeleting(false);
    }
  };

  const paginated = useMemo(
    () => paginateItems(items, page, AGENTS_PAGE_SIZE),
    [items, page]
  );

  useEffect(() => {
    if (page !== paginated.currentPage) setPage(paginated.currentPage);
  }, [page, paginated.currentPage]);

  return (
    <PageShell>
      <header className="border-b border-gov-gray-200 pb-4 dark:border-dark-border">
        <div className="flex flex-col justify-between gap-4 md:flex-row md:items-end">
          <div>
            <h1 className="text-2xl font-bold text-gov-gray-900 dark:text-dark-text">
              {isAdmin ? 'Workers' : 'Mis agentes'}
            </h1>
            <p className="mt-1 text-sm text-gov-gray-600 dark:text-dark-muted">
              {isAdmin
                ? 'Catálogo DB-first: crear, editar capacidades y desactivar workers.'
                : 'Agentes disponibles para conversar o usar como base.'}
            </p>
          </div>
          <button
            type="button"
            onClick={() => setCreateOpen(true)}
            className="inline-flex items-center gap-2 rounded-lg bg-gov-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-gov-blue-800"
          >
            <Plus size={16} />
            Nuevo agente
          </button>
        </div>
      </header>

      <CreateAgentDialog open={createOpen} onClose={() => setCreateOpen(false)} onCreated={reload} />

      {error ? (
        <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/30 dark:text-red-300">
          {error}
        </p>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-12">
        <section className="lg:col-span-12">
          {items.length === 0 ? (
            <EmptyState
              variant="empty"
              customMessage={
                error ?? (isAdmin ? 'No hay workers o el gateway no responde.' : 'Aún no hay agentes disponibles.')
              }
            />
          ) : (
            <AgentsGrid
              items={paginated.items}
              page={paginated.currentPage}
              totalPages={paginated.totalPages}
              totalItems={paginated.totalItems}
              canWrite={canWrite}
              isAdmin={isAdmin}
              onPageChange={setPage}
              onRequestDeactivate={setPendingDeactivate}
              onRequestHardDelete={setPendingHardDelete}
            />
          )}
        </section>
      </div>

      <ConfirmDangerModal
        isOpen={!!pendingDeactivate}
        title="Desactivar del catálogo"
        description="Oculta este worker del catálogo DB-first para tu tenant. No borra carpetas de templates ni archivos en disco."
        confirmLabel="Sí, desactivar del catálogo"
        isLoading={deleting}
        details={
          pendingDeactivate
            ? [
                { label: 'Worker ID', value: pendingDeactivate.id },
                { label: 'Nombre', value: pendingDeactivate.name ?? '—' },
                { label: 'Origen', value: pendingDeactivate.source ?? 'catalog' },
                { label: 'Visibilidad', value: pendingDeactivate.visibility ?? 'private' },
              ]
            : []
        }
        onCancel={() => !deleting && setPendingDeactivate(null)}
        onConfirm={confirmDeactivate}
      />

      <ConfirmDangerModal
        isOpen={!!pendingHardDelete}
        title="Eliminar definitivo"
        description="Elimina físicamente este worker y sus relaciones DB-first. No borra carpetas de templates legacy."
        confirmLabel="Sí, eliminar definitivamente"
        isLoading={deleting}
        details={
          pendingHardDelete
            ? [
                { label: 'Worker ID', value: pendingHardDelete.id },
                { label: 'Nombre', value: pendingHardDelete.name ?? '—' },
                { label: 'Relaciones', value: 'versions, contexts, skills, capabilities y proyectos' },
              ]
            : []
        }
        onCancel={() => !deleting && setPendingHardDelete(null)}
        onConfirm={confirmHardDelete}
      />
    </PageShell>
  );
}

function AgentsGrid({
  items,
  page,
  totalPages,
  totalItems,
  canWrite,
  isAdmin,
  onPageChange,
  onRequestDeactivate,
  onRequestHardDelete,
}: {
  items: TemplateSummary[];
  page: number;
  totalPages: number;
  totalItems: number;
  canWrite: boolean;
  isAdmin: boolean;
  onPageChange: (page: number) => void;
  onRequestDeactivate: (t: TemplateSummary) => void;
  onRequestHardDelete: (t: TemplateSummary) => void;
}) {
  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-2 rounded-xl border border-gov-gray-200 bg-white px-4 py-3 dark:border-dark-border dark:bg-dark-surface sm:flex-row sm:items-center sm:justify-between">
        <p className="text-sm font-semibold text-gov-gray-900 dark:text-dark-text">
          {totalItems} {totalItems === 1 ? 'agente' : 'agentes'} en catálogo
        </p>
        <PaginationControls page={page} totalPages={totalPages} onPageChange={onPageChange} />
      </div>

      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
        {items.map((agent) => (
          <AgentCard
            key={agent.id}
            agent={agent}
            canWrite={canWrite}
            isAdmin={isAdmin}
            onRequestDeactivate={onRequestDeactivate}
            onRequestHardDelete={onRequestHardDelete}
          />
        ))}
      </div>
    </div>
  );
}

function AgentCard({
  agent,
  canWrite,
  isAdmin,
  onRequestDeactivate,
  onRequestHardDelete,
}: {
  agent: TemplateSummary;
  canWrite: boolean;
  isAdmin: boolean;
  onRequestDeactivate: (t: TemplateSummary) => void;
  onRequestHardDelete: (t: TemplateSummary) => void;
}) {
  const metadata = agentMetadata(agent);
  const subtitle = agentCardSubtitle(agent);
  const Icon = agentWorkerIcon(agent.id);
  const isCatalogManaged = agent.source === 'catalog' && Boolean(agent.worker_uid);
  const isProtectedWorker = agent.id === 'default';
  const showLifecycleActions = canWrite && isCatalogManaged && !isProtectedWorker;

  return (
    <article className="flex min-h-[168px] flex-col rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface">
      <div className="border-b border-gov-gray-100 px-4 py-3 dark:border-dark-border">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-gov-blue-50 text-gov-blue-700 dark:bg-dark-bg dark:text-dark-cyan">
            <Icon size={20} strokeWidth={2.25} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-start justify-between gap-2">
              <h2 className="line-clamp-2 text-base font-semibold leading-snug text-gov-gray-900 dark:text-dark-text">
                {agent.name ?? agent.id}
              </h2>
              <span className="shrink-0 rounded-full bg-gov-gray-100 px-2 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-gov-gray-500 dark:bg-dark-bg dark:text-dark-muted">
                {isAdmin ? 'worker' : 'agente'}
              </span>
            </div>
            <p className="mt-0.5 line-clamp-1 font-mono text-[11px] text-gov-gray-400 dark:text-dark-muted">
              {agent.id}
            </p>
          </div>
        </div>
      </div>

      <div className="flex flex-1 flex-col px-4 py-3">
        {subtitle ? (
          <p className="line-clamp-2 text-xs leading-relaxed text-gov-gray-600 dark:text-dark-muted">{subtitle}</p>
        ) : null}

        {metadata.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {metadata.map((item) => (
              <span
                key={`${item.label}:${item.value}`}
                className="rounded-full bg-gov-gray-50 px-2 py-0.5 text-[10px] font-medium text-gov-gray-600 dark:bg-dark-bg dark:text-dark-muted"
              >
                {item.label}: <span className="font-mono">{item.value}</span>
              </span>
            ))}
          </div>
        )}

        {agent.load_error && (
          <p className="mt-2 rounded-lg bg-red-50 px-2 py-1.5 text-xs text-red-700 dark:bg-red-950/30 dark:text-red-300">
            {agent.load_error}
          </p>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-1.5 border-t border-gov-gray-100 px-4 py-2.5 dark:border-dark-border">
        <Link
          href={`/templates/${agent.id}`}
          className="inline-flex items-center rounded-lg bg-gov-blue-700 px-3 py-1.5 text-xs font-semibold text-white hover:bg-gov-blue-800"
        >
          {isAdmin ? 'Editar' : 'Abrir'}
        </Link>
        {showLifecycleActions ? (
          <div className="ml-auto flex items-center gap-1">
            <button
              type="button"
              onClick={() => onRequestDeactivate(agent)}
              title="Desactivar del catálogo"
              aria-label={`Desactivar ${agent.name ?? agent.id}`}
              className="inline-flex items-center gap-1 rounded-lg border border-amber-200 px-2.5 py-1.5 text-xs font-semibold text-amber-800 hover:bg-amber-50 dark:border-amber-900/50 dark:text-amber-300 dark:hover:bg-amber-950/30"
            >
              <Power size={14} />
              <span className="hidden sm:inline">Desactivar</span>
            </button>
            <button
              type="button"
              onClick={() => onRequestHardDelete(agent)}
              title="Eliminar definitivo"
              aria-label={`Eliminar ${agent.name ?? agent.id}`}
              className="inline-flex items-center gap-1 rounded-lg border border-red-200 px-2.5 py-1.5 text-xs font-semibold text-red-700 hover:bg-red-50 dark:border-red-900/50 dark:text-red-300 dark:hover:bg-red-950/30"
            >
              <Trash2 size={14} />
              <span className="hidden sm:inline">Eliminar</span>
            </button>
          </div>
        ) : null}
      </div>
    </article>
  );
}

function PaginationControls({
  page,
  totalPages,
  onPageChange,
}: {
  page: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}) {
  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        onClick={() => onPageChange(page - 1)}
        disabled={page <= 1}
        className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-3 py-1.5 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-40 dark:border-dark-border"
      >
        <ChevronLeft size={14} />
        Anterior
      </button>
      <span className="min-w-16 text-center text-xs font-medium text-gov-gray-500 dark:text-dark-muted">
        {page}/{totalPages}
      </span>
      <button
        type="button"
        onClick={() => onPageChange(page + 1)}
        disabled={page >= totalPages}
        className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-3 py-1.5 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-40 dark:border-dark-border"
      >
        Siguiente
        <ChevronRight size={14} />
      </button>
    </div>
  );
}
