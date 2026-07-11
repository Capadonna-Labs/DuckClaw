'use client';

import { useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { ViewChrome, type EmbeddedViewProps } from '@/components/admin/embeddedView';
import { ConsoleUsersPanel } from '@/components/access/ConsoleUsersPanel';
import { SharedGrantsPanel } from '@/components/access/SharedGrantsPanel';
import { useAuthStore } from '@/store/authStore';

type TabId = 'console' | 'shared';

const TABS: { id: TabId; label: string }[] = [
  { id: 'console', label: 'Usuarios web' },
  { id: 'shared', label: 'Bases compartidas' },
];

function parseTab(raw: string | null): TabId {
  if (raw === 'shared') return 'shared';
  return 'console';
}

export default function AccessPageView({ embedded = false }: EmbeddedViewProps) {
  const { usuario } = useAuthStore();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [tab, setTab] = useState<TabId>(() => parseTab(searchParams.get('accessTab') ?? searchParams.get('tab')));
  const [tenantId, setTenantId] = useState('default');

  useEffect(() => {
    if (searchParams.get('tab') === 'telegram') {
      router.replace('/integraciones?tab=telegram');
      return;
    }
    setTab(parseTab(searchParams.get('accessTab') ?? searchParams.get('tab')));
  }, [router, searchParams]);

  useEffect(() => {
    if (usuario?.rol !== 'admin') {
      router.replace('/overview');
    }
  }, [usuario?.rol, router]);

  const selectTab = (next: TabId) => {
    setTab(next);
    router.replace(`/administracion?tab=acceso&accessTab=${next}`, { scroll: false });
  };

  if (usuario?.rol !== 'admin') {
    return null;
  }

  return (
    <ViewChrome embedded={embedded}>
      <div className="flex flex-wrap items-center gap-2 border-b dark:border-dark-border pb-3">
        {TABS.map((t) => (
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

      {tab === 'console' && (
        <section className="rounded-3xl border border-gov-gray-100 bg-white p-6 shadow-sm dark:border-dark-border dark:bg-dark-surface">
          <ConsoleUsersPanel />
        </section>
      )}

      {tab === 'shared' && (
        <section className="rounded-3xl border border-gov-gray-100 bg-white p-6 shadow-sm dark:border-dark-border dark:bg-dark-surface">
          <SharedGrantsPanel tenantId={tenantId} />
        </section>
      )}
    </ViewChrome>
  );
}
