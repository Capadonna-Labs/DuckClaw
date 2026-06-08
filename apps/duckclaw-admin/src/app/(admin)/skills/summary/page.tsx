'use client';

import Link from 'next/link';
import { PageShell } from '@/components/admin/PageShell';
import { SkillSummary } from '@/components/skills/SkillSummary';
import { useSkillsCatalog } from '@/components/skills/useSkillsCatalog';

export default function SkillsSummaryPage() {
  const { globalSkills, localSkills, error } = useSkillsCatalog();

  return (
    <PageShell>
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Resumen de skills</h1>
        <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
          Una vista para inventario, sin crear ni listar detalle.
        </p>
      </header>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <SkillSummary globalCount={globalSkills.length} localCount={localSkills.length} />
      <Link href="/skills" className="text-sm font-bold text-gov-blue-700 dark:text-dark-cyan">
        Volver a Skills
      </Link>
    </PageShell>
  );
}
