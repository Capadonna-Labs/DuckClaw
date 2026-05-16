'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { adminService } from '@/services/adminService';
import type { TemplateSummary } from '@/types/admin';
import EmptyState from '@/components/shared/EmptyState';
import { Search } from 'lucide-react';

export default function TemplatesPage() {
  const [items, setItems] = useState<TemplateSummary[]>([]);
  const [q, setQ] = useState('');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminService
      .listTemplates()
      .then(setItems)
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, []);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    if (!needle) return items;
    return items.filter(
      (t) =>
        t.id.toLowerCase().includes(needle) ||
        (t.name ?? '').toLowerCase().includes(needle) ||
        (t.schema_name ?? '').toLowerCase().includes(needle)
    );
  }, [items, q]);

  return (
    <div className="space-y-6">
      <header className="flex flex-col md:flex-row md:items-end justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black text-gov-gray-900 dark:text-dark-text">Plantillas</h1>
          <p className="text-sm text-gov-gray-500 dark:text-dark-muted">
            Workers en forge/templates
          </p>
        </div>
        <Link
          href="/projects/new"
          className="px-4 py-2 bg-gov-blue-700 text-white text-sm font-bold rounded-xl"
        >
          Nuevo proyecto
        </Link>
      </header>

      <motionSearch q={q} setQ={setQ} />

      {error && <p className="text-red-600 text-sm">{error}</p>}

      {filtered.length === 0 ? (
        <EmptyState
          variant="empty"
          customMessage={error ?? 'No hay workers o el gateway no responde.'}
        />
      ) : (
        <TemplatesTable items={filtered} />
      )}
    </div>
  );
}

function motionSearch({ q, setQ }: { q: string; setQ: (v: string) => void }) {
  return (
    <div className="relative max-w-md">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gov-gray-400" size={18} />
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Buscar por id, nombre o schema…"
        className="w-full pl-10 pr-4 py-2.5 rounded-xl border border-gov-gray-200 dark:border-dark-border dark:bg-dark-surface"
      />
    </div>
  );
}

function TemplatesTable({ items }: { items: TemplateSummary[] }) {
  return (
    <div className="overflow-hidden rounded-2xl border border-gov-gray-100 dark:border-dark-border bg-white dark:bg-dark-surface">
      <table className="w-full text-sm">
        <thead className="bg-gov-gray-50 dark:bg-dark-bg text-left">
          <tr>
            <th className="px-4 py-3 font-bold">ID</th>
            <th className="px-4 py-3 font-bold">Nombre</th>
            <th className="px-4 py-3 font-bold">Schema</th>
            <th className="px-4 py-3 font-bold">Temp</th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody>
          {items.map((t, i) => (
            <tr
              key={t.id}
              className={
                i % 2 === 0
                  ? 'border-t border-gov-gray-100 dark:border-dark-border'
                  : 'border-t border-gov-gray-100 dark:border-dark-border bg-gov-gray-50/50 dark:bg-dark-bg/30'
              }
            >
              <td className="px-4 py-3 font-mono text-xs">{t.id}</td>
              <td className="px-4 py-3">{t.name ?? '—'}</td>
              <td className="px-4 py-3 font-mono text-xs">{t.schema_name ?? '—'}</td>
              <td className="px-4 py-3">{t.temperature ?? '—'}</td>
              <td className="px-4 py-3 text-right">
                <Link
                  href={`/templates/${t.id}`}
                  className="text-gov-blue-700 dark:text-dark-cyan font-semibold hover:underline"
                >
                  Editar
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
