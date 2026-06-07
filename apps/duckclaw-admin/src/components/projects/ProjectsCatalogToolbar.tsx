'use client';

import type { WorkspaceProjectsQuery } from '@/services/adminService';

type CatalogSort = NonNullable<WorkspaceProjectsQuery['sort']>;
type CatalogDirection = NonNullable<WorkspaceProjectsQuery['direction']>;
type CatalogStatus = NonNullable<WorkspaceProjectsQuery['status']>;

export type ProjectsCatalogToolbarProps = {
  query: string;
  status: CatalogStatus;
  sort: CatalogSort;
  direction: CatalogDirection;
  limit: number;
  onQueryChange: (value: string) => void;
  onStatusChange: (value: CatalogStatus) => void;
  onSortChange: (value: CatalogSort) => void;
  onDirectionChange: (value: CatalogDirection) => void;
  onLimitChange: (value: number) => void;
};

const sortOptions: { value: CatalogSort; label: string }[] = [
  { value: 'updated_at', label: 'Actualizado' },
  { value: 'created_at', label: 'Creado' },
  { value: 'name', label: 'Nombre' },
  { value: 'agent_count', label: 'Agentes' },
];

const directionOptions: { value: CatalogDirection; label: string }[] = [
  { value: 'desc', label: 'Descendente' },
  { value: 'asc', label: 'Ascendente' },
];

const statusOptions: { value: CatalogStatus; label: string }[] = [
  { value: 'active', label: 'Activos' },
  { value: 'inactive', label: 'Inactivos' },
  { value: 'all', label: 'Todos' },
];

const limitOptions = [10, 25, 50, 100];

export function ProjectsCatalogToolbar({
  query,
  status,
  sort,
  direction,
  limit,
  onQueryChange,
  onStatusChange,
  onSortChange,
  onDirectionChange,
  onLimitChange,
}: ProjectsCatalogToolbarProps) {
  return (
    <div className="grid gap-3 rounded-2xl border border-gov-blue-100 bg-white p-4 dark:border-dark-border dark:bg-dark-surface md:grid-cols-[minmax(0,1fr)_140px_180px_140px_120px]">
      <label className="flex flex-col gap-1 text-xs font-bold uppercase tracking-wide text-gov-gray-500 dark:text-dark-muted">
        Buscar
        <input
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          placeholder="Buscar por nombre, descripción o ID"
          className="rounded-xl border border-gov-blue-100 px-3 py-2 text-sm font-normal normal-case tracking-normal text-gov-gray-900 outline-none focus:border-gov-blue-500 dark:border-dark-border dark:bg-dark-bg dark:text-dark-text"
        />
      </label>

      <label className="flex flex-col gap-1 text-xs font-bold uppercase tracking-wide text-gov-gray-500 dark:text-dark-muted">
        Estado
        <select
          value={status}
          onChange={(event) => onStatusChange(event.target.value as CatalogStatus)}
          className="rounded-xl border border-gov-blue-100 px-3 py-2 text-sm font-normal normal-case tracking-normal text-gov-gray-900 outline-none focus:border-gov-blue-500 dark:border-dark-border dark:bg-dark-bg dark:text-dark-text"
        >
          {statusOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1 text-xs font-bold uppercase tracking-wide text-gov-gray-500 dark:text-dark-muted">
        Ordenar por
        <select
          value={sort}
          onChange={(event) => onSortChange(event.target.value as CatalogSort)}
          className="rounded-xl border border-gov-blue-100 px-3 py-2 text-sm font-normal normal-case tracking-normal text-gov-gray-900 outline-none focus:border-gov-blue-500 dark:border-dark-border dark:bg-dark-bg dark:text-dark-text"
        >
          {sortOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1 text-xs font-bold uppercase tracking-wide text-gov-gray-500 dark:text-dark-muted">
        Dirección
        <select
          value={direction}
          onChange={(event) => onDirectionChange(event.target.value as CatalogDirection)}
          className="rounded-xl border border-gov-blue-100 px-3 py-2 text-sm font-normal normal-case tracking-normal text-gov-gray-900 outline-none focus:border-gov-blue-500 dark:border-dark-border dark:bg-dark-bg dark:text-dark-text"
        >
          {directionOptions.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>

      <label className="flex flex-col gap-1 text-xs font-bold uppercase tracking-wide text-gov-gray-500 dark:text-dark-muted">
        Límite
        <select
          value={limit}
          onChange={(event) => onLimitChange(Number(event.target.value))}
          className="rounded-xl border border-gov-blue-100 px-3 py-2 text-sm font-normal normal-case tracking-normal text-gov-gray-900 outline-none focus:border-gov-blue-500 dark:border-dark-border dark:bg-dark-bg dark:text-dark-text"
        >
          {limitOptions.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
    </div>
  );
}
