'use client';

import Link from 'next/link';
import { Plus, RefreshCw } from 'lucide-react';
import type { WorkspaceProjectsQuery } from '@/services/adminService';

type CatalogSort = NonNullable<WorkspaceProjectsQuery['sort']>;
type CatalogStatus = NonNullable<WorkspaceProjectsQuery['status']>;

export type ProjectsControlPanelProps = {
  canWrite: boolean;
  query: string;
  status: CatalogStatus;
  sort: CatalogSort;
  limit: number;
  loading?: boolean;
  onQueryChange: (value: string) => void;
  onStatusChange: (value: CatalogStatus) => void;
  onSortChange: (value: CatalogSort) => void;
  onLimitChange: (value: number) => void;
  onRefresh: () => void;
};

const sortOptions: { value: CatalogSort; label: string }[] = [
  { value: 'updated_at', label: 'Actualizado' },
  { value: 'created_at', label: 'Creado' },
  { value: 'name', label: 'Nombre' },
  { value: 'agent_count', label: 'Agentes' },
];

const statusOptions: { value: CatalogStatus; label: string }[] = [
  { value: 'active', label: 'Activos' },
  { value: 'inactive', label: 'Inactivos' },
  { value: 'all', label: 'Todos' },
];

const limitOptions = [10, 25, 50, 100];

export function ProjectsControlPanel({
  canWrite,
  query,
  status,
  sort,
  limit,
  loading = false,
  onQueryChange,
  onStatusChange,
  onSortChange,
  onLimitChange,
  onRefresh,
}: ProjectsControlPanelProps) {
  return (
    <aside className="rounded-2xl border border-gov-gray-100 bg-white p-4 shadow-sm dark:border-dark-border dark:bg-dark-surface lg:sticky lg:top-4 space-y-4">
      <div className="space-y-3">
        <h2 className="text-sm font-black text-gov-gray-900 dark:text-dark-text">Filtros</h2>
        <label className="block text-xs font-bold text-gov-gray-700 dark:text-dark-text">
          Buscar
          <input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder="Nombre, descripción o ID"
            className="mt-1 w-full rounded-xl border border-gov-gray-200 px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
          />
        </label>
        <label className="block text-xs font-bold text-gov-gray-700 dark:text-dark-text">
          Estado
          <select
            value={status}
            onChange={(event) => onStatusChange(event.target.value as CatalogStatus)}
            className="mt-1 w-full rounded-xl border border-gov-gray-200 px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
          >
            {statusOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs font-bold text-gov-gray-700 dark:text-dark-text">
          Ordenar por
          <select
            value={sort}
            onChange={(event) => onSortChange(event.target.value as CatalogSort)}
            className="mt-1 w-full rounded-xl border border-gov-gray-200 px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
          >
            {sortOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </label>
        <label className="block text-xs font-bold text-gov-gray-700 dark:text-dark-text">
          Por página
          <select
            value={limit}
            onChange={(event) => onLimitChange(Number(event.target.value))}
            className="mt-1 w-full rounded-xl border border-gov-gray-200 px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
          >
            {limitOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      </div>
      <button
        type="button"
        onClick={onRefresh}
        disabled={loading}
        className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-gov-gray-200 px-3 py-2 text-xs font-bold text-gov-blue-800 disabled:opacity-50 dark:border-dark-border dark:text-dark-cyan"
      >
        <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
        Refrescar
      </button>
      {canWrite ? (
        <Link
          href="/projects/orchestrator"
          className="inline-flex w-full items-center justify-center gap-2 rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-black text-white hover:bg-gov-blue-900"
        >
          <Plus size={16} />
          Nuevo proyecto
        </Link>
      ) : null}
    </aside>
  );
}
