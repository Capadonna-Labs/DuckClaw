'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { readDeveloperMode } from '@/lib/developerMode';

export default function SkillsNewRedirectPage() {
  const router = useRouter();

  useEffect(() => {
    const target = readDeveloperMode()
      ? '/plataforma?tab=skills&skillsTab=create'
      : '/plataforma?tab=skills&skillsTab=platform';
    router.replace(target);
  }, [router]);

  return (
    <p className="p-8 text-sm text-gov-gray-500 dark:text-dark-muted">Redirigiendo…</p>
  );
}
