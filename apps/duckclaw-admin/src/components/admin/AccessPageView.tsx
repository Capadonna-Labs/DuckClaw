'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ViewChrome, type EmbeddedViewProps } from '@/components/admin/embeddedView';
import SettingsSection from '@/components/settings/SettingsSection';
import { AccountSettingsPanel } from '@/components/settings/AccountSettingsPanel';
import { ConsoleUsersPanel } from '@/components/access/ConsoleUsersPanel';
import { SharedGrantsPanel } from '@/components/access/SharedGrantsPanel';
import { PermissionsMatrix } from '@/components/access/PermissionsMatrix';
import { AccessPersistenceInfo } from '@/components/access/AccessPersistenceInfo';
import { useAuthStore } from '@/store/authStore';
import { adminService } from '@/services/adminService';
import { Shield, Users } from 'lucide-react';

type TabId = 'cuenta' | 'console' | 'shared';

const TABS: { id: TabId; label: string }[] = [
  { id: 'cuenta', label: 'Mi cuenta' },
  { id: 'console', label: 'Consola' },
  { id: 'shared', label: 'Bases compartidas' },
];

const EMBEDDED_TABS = TABS.filter((tab) => tab.id !== 'cuenta');

function parseTab(raw: string | null): TabId {
  if (raw === 'cuenta' || raw === 'console' || raw === 'shared') {
    return raw;
  }
  return 'cuenta';
}

export default function AccessPageView({ embedded = false }: EmbeddedViewProps) {
  const { usuario, logout } = useAuthStore();
  const router = useRouter();
  const searchParams = useSearchParams();
  const visibleTabs = embedded ? EMBEDDED_TABS : TABS;
  const [tab, setTab] = useState<TabId>(() => {
    const parsed = parseTab(searchParams.get('accessTab') ?? searchParams.get('tab'));
    if (embedded && parsed === 'cuenta') return 'console';
    return parsed;
  });
  const [tenantId, setTenantId] = useState('default');
  const [overview, setOverview] = useState<{
    console_users: number;
    telegram_users: number;
    shared_grants: number;
    db_path?: string;
    db_exists?: boolean;
  } | null>(null);

  useEffect(() => {
    if (searchParams.get('tab') === 'telegram') {
      router.replace('/integraciones?tab=telegram');
      return;
    }
    setTab(() => {
      const parsed = parseTab(searchParams.get('accessTab') ?? searchParams.get('tab'));
      if (embedded && parsed === 'cuenta') return 'console';
      return parsed;
    });
  }, [embedded, router, searchParams]);

  useEffect(() => {
    if (usuario?.rol !== 'admin') {
      router.replace('/overview');
      return;
    }
    adminService
      .getAccessOverview(tenantId)
      .then((r) =>
        setOverview({
          console_users: r.console_users,
          telegram_users: r.telegram_users,
          shared_grants: r.shared_grants,
          db_path: r.db_path,
          db_exists: r.db_exists,
        })
      )
      .catch(() => setOverview(null));
  }, [usuario?.rol, router, tenantId]);

  const selectTab = (next: TabId) => {
    setTab(next);
    router.replace(`/administracion?tab=acceso&accessTab=${next}`, { scroll: false });
  };

  const handleLogout = async () => {
    await logout();
    router.replace('/login');
  };

  if (usuario?.rol !== 'admin') {
    return null;
  }

  return (
    <ViewChrome embedded={embedded}>
      {!embedded && (
        <header className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-3xl font-black dark:text-dark-text">Usuarios y roles</h1>
            <p className="text-sm text-gov-gray-500 dark:text-dark-muted mt-1">
              Tu cuenta, usuarios de la consola web y permisos sobre bases compartidas
            </p>
            {overview && tab !== 'cuenta' && (
              <p className="text-xs text-gov-gray-500 mt-2 font-mono">
                consola {overview.console_users} · grants {overview.shared_grants}
              </p>
            )}
          </div>
          {tab !== 'cuenta' && <PermissionsMatrix />}
        </header>
      )}

      {embedded && tab !== 'cuenta' && (
        <div className="flex flex-wrap items-center justify-between gap-4">
          {overview && (
            <p className="text-xs text-gov-gray-500 font-mono">
              consola {overview.console_users} · grants {overview.shared_grants}
            </p>
          )}
          <PermissionsMatrix />
        </div>
      )}

      {tab !== 'cuenta' && (
        <AccessPersistenceInfo
          dbPath={overview?.db_path}
          dbExists={overview?.db_exists}
          activeTab={tab}
        />
      )}

      <div className="flex flex-wrap gap-2 border-b dark:border-dark-border pb-2">
        {visibleTabs.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => selectTab(t.id)}
            className={`px-4 py-2 rounded-xl text-sm font-bold ${
              tab === t.id
                ? 'bg-gov-blue-700 text-white'
                : 'bg-gov-gray-100 dark:bg-dark-bg text-gov-gray-600 dark:text-dark-muted'
            }`}
          >
            {t.label}
          </button>
        ))}
        {tab === 'shared' && (
          <input
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
            className="ml-auto px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-bg text-sm font-mono"
            placeholder="tenant_id"
          />
        )}
      </div>

      {tab === 'cuenta' && <AccountSettingsPanel onLogout={handleLogout} />}

      {tab === 'console' && (
        <SettingsSection
          titulo="Usuarios consola"
          descripcion="Personas que pueden entrar a la consola web (login email/contraseña)"
          icono={<Shield size={22} />}
        >
          <ConsoleUsersPanel />
        </SettingsSection>
      )}

      {tab === 'shared' && (
        <SettingsSection
          titulo="Bases compartidas"
          descripcion="Permisos de acceso por tenant"
          icono={<Users size={22} />}
        >
          <SharedGrantsPanel tenantId={tenantId} />
        </SettingsSection>
      )}
    </ViewChrome>
  );
}
