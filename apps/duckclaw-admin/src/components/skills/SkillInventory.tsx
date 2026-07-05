'use client';

import Link from 'next/link';
import { useState } from 'react';
import { Plus, Search, Trash2 } from 'lucide-react';
import type { SkillCatalogItem } from '@/services/adminService';
import { filterSkills } from '@/components/skills/useSkillsCatalog';

export function SkillInventory({
  title,
  subtitle,
  items,
  showWorker = false,
  emptyHint,
  onCreateClick,
  onHardDelete,
  canDelete = false,
}: {
  title: string;
  subtitle?: string;
  items: SkillCatalogItem[];
  showWorker?: boolean;
  emptyHint?: string;
  onCreateClick?: () => void;
  onHardDelete?: (skill: SkillCatalogItem) => void;
  canDelete?: boolean;
}) {
  const [q, setQ] = useState('');
  const filtered = filterSkills(items, q);

  return (
    <section className="space-y-4 rounded-3xl border border-gov-gray-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">{title}</h2>
          {subtitle ? (
            <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">{subtitle}</p>
          ) : null}
          <p className="mt-1 text-xs text-gov-gray-400 dark:text-dark-muted">
            {filtered.length}/{items.length} visibles
          </p>
        </div>
        <div className="relative max-w-md flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gov-gray-400" size={18} />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar por nombre o ruta…"
            maxLength={50}
            className="w-full rounded-xl border py-2 pl-10 pr-3 text-sm dark:border-dark-border dark:bg-dark-bg"
          />
        </div>
      </div>
      <SkillTable
        items={filtered}
        showWorker={showWorker}
        emptyHint={emptyHint}
        onCreateClick={onCreateClick}
        onHardDelete={onHardDelete}
        canDelete={canDelete}
      />
    </section>
  );
}

function SkillTable({
  items,
  showWorker,
  emptyHint,
  onCreateClick,
  onHardDelete,
  canDelete,
}: {
  items: SkillCatalogItem[];
  showWorker?: boolean;
  emptyHint?: string;
  onCreateClick?: () => void;
  onHardDelete?: (skill: SkillCatalogItem) => void;
  canDelete?: boolean;
}) {
  if (items.length === 0) {
    return (
      <div className="rounded-2xl border border-dashed border-gov-gray-200 p-6 text-center dark:border-dark-border">
        <p className="text-sm font-semibold text-gov-gray-700 dark:text-dark-text">Sin skills en este alcance</p>
        {emptyHint ? (
          <p className="mx-auto mt-2 max-w-lg text-xs leading-relaxed text-gov-gray-500 dark:text-dark-muted">
            {emptyHint}
          </p>
        ) : null}
        {onCreateClick ? (
          <button
            type="button"
            onClick={onCreateClick}
            className="mt-4 inline-flex items-center gap-2 rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-black text-white hover:bg-gov-blue-800"
          >
            <Plus size={16} />
            Crear skill
          </button>
        ) : null}
      </div>
    );
  }

  return (
    <div className="max-h-[50vh] overflow-x-auto rounded-2xl border dark:border-dark-border">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-gov-gray-50 dark:bg-dark-bg">
          <tr>
            <th className="px-3 py-2 text-left">Nombre</th>
            {showWorker && <th className="px-3 py-2 text-left">Agente</th>}
            <th className="px-3 py-2 text-left">Implementación</th>
            <th className="px-3 py-2 text-left">Acción</th>
          </tr>
        </thead>
        <tbody>
          {items.map((skill) => (
            <tr key={`${skill.worker_id ?? ''}-${skill.id}`} className="border-t dark:border-dark-border">
              <td className="px-3 py-2 font-mono text-xs font-bold">{skill.id}</td>
              {showWorker && (
                <td className="px-3 py-2 text-xs">
                  {skill.worker_id ? (
                    <Link
                      href={`/templates/${encodeURIComponent(skill.worker_id)}`}
                      className="font-bold text-gov-blue-700 underline dark:text-dark-cyan"
                    >
                      {skill.worker_id}
                    </Link>
                  ) : (
                    '—'
                  )}
                </td>
              )}
              <td className="max-w-md px-3 py-2 font-mono text-[10px] text-gov-gray-500">{skill.path}</td>
              <td className="px-3 py-2 text-xs">
                <div className="flex flex-wrap items-center gap-2">
                  {skill.worker_id ? (
                    <Link
                      href={`/templates/${encodeURIComponent(skill.worker_id)}`}
                      className="font-bold text-gov-blue-700 dark:text-dark-cyan"
                    >
                      Editor
                    </Link>
                  ) : (
                    <Link href="/templates" className="font-bold text-gov-blue-700 dark:text-dark-cyan">
                      Activar en agente
                    </Link>
                  )}
                  {canDelete && onHardDelete && !skill.worker_id ? (
                    <button
                      type="button"
                      onClick={() => onHardDelete(skill)}
                      className="inline-flex items-center gap-1 font-bold text-red-700 hover:underline dark:text-red-300"
                      title="Eliminar definitivamente de DuckDB"
                    >
                      <Trash2 size={12} />
                      Borrar
                    </button>
                  ) : null}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
