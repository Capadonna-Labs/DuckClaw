'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store/authStore';
import { isAdminRole } from '@/lib/roles';

export default function SettingsRedirectPage() {
  const router = useRouter();
  const { usuario } = useAuthStore();

  useEffect(() => {
    if (isAdminRole(usuario?.rol)) {
      router.replace('/administracion?tab=acceso');
      return;
    }
    router.replace('/overview');
  }, [router, usuario?.rol]);

  return (
    <p className="p-8 text-sm text-gov-gray-500 dark:text-dark-muted">Redirigiendo…</p>
  );
}
