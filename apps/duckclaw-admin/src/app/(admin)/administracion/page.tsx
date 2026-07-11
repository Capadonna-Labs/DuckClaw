'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { AdminHubShell } from '@/components/admin/AdminHubShell';
import AccessPageView from '@/components/admin/AccessPageView';
import AuditPageView from '@/components/admin/AuditPageView';
import { useAuthStore } from '@/store/authStore';

const TABS = [
  { id: 'acceso', label: 'Acceso', hint: 'Usuarios web y permisos DuckDB compartido' },
  { id: 'auditoria', label: 'Auditoría', hint: 'Registro de acciones admin' },
] as const;

type AdministracionTab = (typeof TABS)[number]['id'];

function parseTab(raw: string | null): AdministracionTab {
  if (raw === 'acceso' || raw === 'auditoria') return raw;
  if (raw === 'cuenta') return 'acceso';
  return 'acceso';
}

function AdministracionHubContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { usuario } = useAuthStore();
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

  if (usuario?.rol !== 'admin') {
    return null;
  }

  return (
    <AdminHubShell
      title="Administración"
      description="Quién entra a la consola y trazabilidad de cambios."
      tabs={TABS}
      activeTabId={tab}
      onSelectTab={(id) => selectTab(parseTab(id))}
    >
      {tab === 'acceso' && <AccessPageView embedded />}
      {tab === 'auditoria' && <AuditPageView embedded />}
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
