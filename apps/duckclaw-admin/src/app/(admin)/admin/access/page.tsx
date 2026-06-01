'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { PageShell } from '@/components/admin/PageShell';
import SettingsSection from '@/components/settings/SettingsSection';
import { ConsoleUsersPanel } from '@/components/access/ConsoleUsersPanel';
import { TelegramUsersPanel } from '@/components/access/TelegramUsersPanel';
import { SharedGrantsPanel } from '@/components/access/SharedGrantsPanel';
import { PermissionsMatrix } from '@/components/access/PermissionsMatrix';
import { AccessPersistenceInfo } from '@/components/access/AccessPersistenceInfo';
import { useAuthStore } from '@/store/authStore';
import { adminService } from '@/services/adminService';
import { Shield, Users } from 'lucide-react';

type TabId = 'console' | 'telegram' | 'shared';

const TABS: { id: TabId; label: string }[] = [
  { id: 'console', label: 'Consola' },
  { id: 'telegram', label: 'Telegram' },
  { id: 'shared', label: 'Bases compartidas' },
];

export default function AccessPage() {
  const { usuario } = useAuthStore();
  const router = useRouter();
  const [tab, setTab] = useState<TabId>('console');
  const [tenantId, setTenantId] = useState('default');
  const [overview, setOverview] = useState<{
    console_users: number;
    telegram_users: number;
    shared_grants: number;
    db_path?: string;
    db_exists?: boolean;
  } | null>(null);

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

  if (usuario?.rol !== 'admin') {
    return null;
  }

  return (
    <PageShell>
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-3xl font-black dark:text-dark-text">Acceso</h1>
          <p className="text-sm text-gov-gray-500 dark:text-dark-muted mt-1">
            Usuarios consola, whitelist Telegram y permisos sobre bases compartidas
          </p>
          {overview && (
            <p className="text-xs text-gov-gray-500 mt-2 font-mono">
              consola {overview.console_users} · telegram {overview.telegram_users} · grants{' '}
              {overview.shared_grants}
            </p>
          )}
        </div>
        <PermissionsMatrix />
      </header>

      <AccessPersistenceInfo
        dbPath={overview?.db_path}
        dbExists={overview?.db_exists}
        activeTab={tab}
        tenantId={tenantId}
      />

      <div className="flex flex-wrap gap-2 border-b dark:border-dark-border pb-2">
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setTab(t.id)}
            className={`px-4 py-2 rounded-xl text-sm font-bold ${
              tab === t.id
                ? 'bg-gov-blue-700 text-white'
                : 'bg-gov-gray-100 dark:bg-dark-bg text-gov-gray-600 dark:text-dark-muted'
            }`}
          >
            {t.label}
          </button>
        ))}
        {(tab === 'telegram' || tab === 'shared') && (
          <input
            value={tenantId}
            onChange={(e) => setTenantId(e.target.value)}
            className="ml-auto px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-bg text-sm font-mono"
            placeholder="tenant_id"
          />
        )}
      </div>

      {tab === 'console' && (
        <SettingsSection
          titulo="Usuarios consola"
          descripcion="Personas que pueden entrar a la consola"
          icono={<Shield size={22} />}
        >
          <ConsoleUsersPanel />
        </SettingsSection>
      )}

      {tab === 'telegram' && (
        <SettingsSection
          titulo="Usuarios Telegram"
          descripcion="Personas autorizadas para usar el bot"
          icono={<Users size={22} />}
        >
          <TelegramUsersPanel tenantId={tenantId} onTenantIdChange={setTenantId} />
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
    </PageShell>
  );
}
