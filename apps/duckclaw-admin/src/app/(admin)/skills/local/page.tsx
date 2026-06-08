'use client';

import Link from 'next/link';
import { PageShell } from '@/components/admin/PageShell';
import { SkillInventory } from '@/components/skills/SkillInventory';
import { useSkillsCatalog } from '@/components/skills/useSkillsCatalog';

export default function LocalSkillsPage() {
  const { localSkills, error } = useSkillsCatalog();

  return (
    <PageShell>
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Skills locales</h1>
        <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
          Vista dedicada a capacidades específicas de cada agente.
        </p>
      </header>
      {error && <p className="text-sm text-red-600">{error}</p>}
      <SkillInventory title="Skills locales" items={localSkills} showWorker />
      <Link href="/skills" className="text-sm font-bold text-gov-blue-700 dark:text-dark-cyan">
        Volver a Skills
      </Link>
    </PageShell>
  );
}
