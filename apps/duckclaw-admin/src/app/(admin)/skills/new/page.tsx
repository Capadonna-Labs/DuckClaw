'use client';

import Link from 'next/link';
import { PageShell } from '@/components/admin/PageShell';
import { SkillCreateForm } from '@/components/skills/SkillCreateForm';

export default function NewSkillPage() {
  return (
    <PageShell>
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Nueva skill</h1>
        <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
          Vista dedicada solo a creación DB-first.
        </p>
      </header>
      <SkillCreateForm />
      <Link href="/skills" className="text-sm font-bold text-gov-blue-700 dark:text-dark-cyan">
        Volver a Skills
      </Link>
    </PageShell>
  );
}
