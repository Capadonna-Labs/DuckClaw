'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store/authStore';
import { isAdminRole } from '@/lib/roles';

/** Redirige la ruta legacy /settings a Mi cuenta o Inicio. */
export default function SettingsRedirectPage() {
  const router = useRouter();
  const { usuario } = useAuthStore();

  useEffect(() => {
    if (isAdminRole(usuario?.rol)) {
      router.replace('/admin/access?tab=cuenta');
      return;
    }
    router.replace('/overview');
  }, [router, usuario?.rol]);

  return (
    <p className="text-sm text-gov-gray-500 dark:text-dark-muted p-8">Redirigiendo…</p>
  );
}
