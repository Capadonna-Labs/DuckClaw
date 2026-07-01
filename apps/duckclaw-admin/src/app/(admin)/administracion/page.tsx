'use client';

import { Suspense, useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { AdminHubShell } from '@/components/admin/AdminHubShell';
import AccessPageView from '@/components/admin/AccessPageView';
import AuditPageView from '@/components/admin/AuditPageView';
import { AccountSettingsPanel } from '@/components/settings/AccountSettingsPanel';
import { useAuthStore } from '@/store/authStore';

const TABS = [
  { id: 'acceso', label: 'Acceso', hint: 'Usuarios consola y grants compartidos' },
  { id: 'auditoria', label: 'Auditoría', hint: 'Registro de acciones admin' },
  { id: 'cuenta', label: 'Mi cuenta', hint: 'Perfil y cierre de sesión' },
] as const;

type AdministracionTab = (typeof TABS)[number]['id'];

function parseTab(raw: string | null): AdministracionTab {
  if (raw === 'acceso' || raw === 'auditoria' || raw === 'cuenta') return raw;
  return 'acceso';
}

function AdministracionHubContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { usuario, logout } = useAuthStore();
  const [tab, setTab] = useState<AdministracionTab>(() => parseTab(searchParams.get('tab')));

  useEffect(() => {
    if (usuario?.rol !== 'admin') {
      router.replace('/overview');
    }
  }, [router, usuario?.rol]);

  useEffect(() => {
    setTab(parseTab(searchParams.get('tab')));
  }, [searchParams]);

  const selectTab = (next: AdministracionTab) => {
    setTab(next);
    router.replace(`/administracion?tab=${next}`, { scroll: false });
  };

  const handleLogout = useCallback(async () => {
    await logout();
    router.replace('/login');
  }, [logout, router]);

  if (usuario?.rol !== 'admin') {
    return null;
  }

  return (
    <AdminHubShell
      title="Administración"
      description="Acceso, auditoría y preferencias de operador."
      tabs={TABS}
      activeTabId={tab}
      onSelectTab={(id) => selectTab(parseTab(id))}
    >
      {tab === 'acceso' && <AccessPageView embedded />}
      {tab === 'auditoria' && <AuditPageView embedded />}
      {tab === 'cuenta' && <AccountSettingsPanel onLogout={handleLogout} />}
    </AdminHubShell>
  );
}

export default function AdministracionHubPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[40vh] items-center justify-center">
          <Loader2 className="animate-spin text-gov-blue-700" size={32} />
        </div>
      }
    >
      <AdministracionHubContent />
    </Suspense>
  );
}
