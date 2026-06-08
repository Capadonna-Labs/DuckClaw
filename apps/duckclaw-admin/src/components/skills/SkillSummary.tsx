'use client';

import Link from 'next/link';
import { Plus } from 'lucide-react';

export function SkillSummary({
  globalCount,
  localCount,
}: {
  globalCount: number;
  localCount: number;
}) {
  const total = globalCount + localCount;
  return (
    <section className="rounded-3xl border border-gov-gray-100 bg-white p-5 shadow-sm dark:border-dark-border dark:bg-dark-surface">
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h2 className="text-lg font-black text-gov-gray-900 dark:text-dark-text">
            Resumen de skills
          </h2>
          <p className="text-sm text-gov-gray-500 dark:text-dark-muted">
            Inventario DB-first separado por alcance.
          </p>
        </div>
        {total === 0 && (
          <Link
            href="/skills/new"
            className="inline-flex w-fit items-center gap-2 rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-black text-white hover:bg-gov-blue-800"
          >
            <Plus size={16} />
            Crear primera skill
          </Link>
        )}
      </div>
      <div className="grid gap-3 md:grid-cols-3">
        <SkillSummaryCard label="Total" value={total} />
        <SkillSummaryCard label="Globales" value={globalCount} />
        <SkillSummaryCard label="Locales" value={localCount} />
      </div>
    </section>
  );
}

function SkillSummaryCard({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl border border-gov-gray-100 bg-gov-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
      <p className="text-xs font-black uppercase tracking-[0.18em] text-gov-gray-500 dark:text-dark-muted">
        {label}
      </p>
      <p className="mt-2 text-3xl font-black text-gov-gray-900 dark:text-dark-text">{value}</p>
    </div>
  );
}
