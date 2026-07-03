'use client';

import Link from 'next/link';
import { Loader2, Puzzle } from 'lucide-react';
import { useSkillCategoriesCatalog } from '@/components/skills/useSkillCategoriesCatalog';

export function PlatformSkillsPanel() {
  const { platformCategories, loading, error } = useSkillCategoriesCatalog();

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-8 text-sm text-gov-gray-500 dark:text-dark-muted">
        <Loader2 size={16} className="animate-spin" />
        Cargando skills de plataforma…
      </div>
    );
  }

  if (error) {
    return <p className="text-sm text-red-600">{error}</p>;
  }

  const total = platformCategories.reduce((n, c) => n + c.skills.length, 0);

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-lg font-black text-gov-gray-900 dark:text-dark-text">
            <Puzzle size={18} aria-hidden />
            Skills de plataforma ({total})
          </h2>
          <p className="mt-1 max-w-2xl text-sm text-gov-gray-500 dark:text-dark-muted">
            Integraciones empaquetadas en el framework. No están en{' '}
            <code className="font-mono text-[10px]">admin_skills</code> — se encienden por nombre en el
            manifest del agente.
          </p>
        </div>
        <Link
          href="/templates"
          className="rounded-xl border border-gov-blue-200 px-3 py-2 text-xs font-bold text-gov-blue-800 dark:border-dark-border dark:text-dark-cyan"
        >
          Activar en agente →
        </Link>
      </div>

      <div className="grid gap-3 md:grid-cols-2">
        {platformCategories.map((category) => (
          <article
            key={category.id}
            className="rounded-2xl border border-gov-gray-100 bg-white p-4 dark:border-dark-border dark:bg-dark-surface"
          >
            <h3 className="text-sm font-black text-gov-gray-900 dark:text-dark-text">{category.title}</h3>
            {category.description ? (
              <p className="mt-1 text-xs text-gov-gray-500 dark:text-dark-muted">{category.description}</p>
            ) : null}
            <ul className="mt-3 flex flex-wrap gap-1.5">
              {category.skills.map((skill) => (
                <li
                  key={skill.id}
                  title={skill.hint || skill.id}
                  className="rounded-lg bg-gov-gray-50 px-2 py-1 font-mono text-[10px] text-gov-gray-700 dark:bg-dark-bg dark:text-dark-muted"
                >
                  {skill.label || skill.id}
                </li>
              ))}
            </ul>
          </article>
        ))}
      </div>
    </section>
  );
}
