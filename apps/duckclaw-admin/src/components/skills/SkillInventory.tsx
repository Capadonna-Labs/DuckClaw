'use client';

import { useState } from 'react';
import { Search } from 'lucide-react';
import type { SkillCatalogItem } from '@/services/adminService';
import { filterSkills } from '@/components/skills/useSkillsCatalog';

export function SkillInventory({
  title,
  items,
  showWorker = false,
}: {
  title: string;
  items: SkillCatalogItem[];
  showWorker?: boolean;
}) {
  const [q, setQ] = useState('');
  const filtered = filterSkills(items, q);
  return (
    <section className="space-y-4 rounded-3xl border border-gov-gray-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">{title}</h2>
          <p className="text-sm text-gov-gray-500 dark:text-dark-muted">
            {filtered.length}/{items.length} visibles
          </p>
        </div>
        <div className="relative max-w-md flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gov-gray-400" size={18} />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar skill..."
            maxLength={50}
            className="w-full rounded-xl border py-2 pl-10 pr-3 text-sm dark:border-dark-border dark:bg-dark-bg"
          />
        </div>
      </div>
      <SkillTable items={filtered} showWorker={showWorker} />
    </section>
  );
}

function SkillTable({
  items,
  showWorker,
}: {
  items: SkillCatalogItem[];
  showWorker?: boolean;
}) {
  if (items.length === 0) {
    return <p className="py-4 text-sm text-gov-gray-500">Sin resultados.</p>;
  }
  return (
    <div className="max-h-[60vh] overflow-x-auto rounded-2xl border dark:border-dark-border">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-gov-gray-50 dark:bg-dark-bg">
          <tr>
            <th className="px-3 py-2 text-left">ID</th>
            {showWorker && <th className="px-3 py-2 text-left">Worker</th>}
            <th className="px-3 py-2 text-left">Ruta</th>
          </tr>
        </thead>
        <tbody>
          {items.map((skill) => (
            <tr key={`${skill.worker_id ?? ''}-${skill.id}`} className="border-t dark:border-dark-border">
              <td className="px-3 py-2 font-mono text-xs">{skill.id}</td>
              {showWorker && <td className="px-3 py-2 text-xs">{skill.worker_id}</td>}
              <td className="px-3 py-2 font-mono text-[10px] text-gov-gray-500">{skill.path}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
