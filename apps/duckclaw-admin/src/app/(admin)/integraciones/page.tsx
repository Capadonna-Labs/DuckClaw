'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { PageShell } from '@/components/admin/PageShell';
import EdgeDevicesPageView from '@/components/integrations/EdgeDevicesPageView';
import SensoryNodePageView from '@/components/integrations/SensoryNodePageView';
import TelegramIntegrationPageView from '@/components/integrations/TelegramIntegrationPageView';
import {
  INTEGRACIONES_TABS,
  parseIntegracionesTab,
  type IntegracionesTabId,
} from '@/config/integracionesNav';

function IntegracionesHubContent() {
  const searchParams = useSearchParams();
  const [tab, setTab] = useState<IntegracionesTabId>(() =>
    parseIntegracionesTab(searchParams.get('tab'))
  );

  useEffect(() => {
    setTab(parseIntegracionesTab(searchParams.get('tab')));
  }, [searchParams]);

  const activeMeta = INTEGRACIONES_TABS.find((t) => t.id === tab);

  return (
    <PageShell>
      <header className="border-b border-gov-gray-200 pb-4 dark:border-dark-border">
        <h1 className="text-2xl font-bold text-gov-gray-900 dark:text-dark-text">
          {activeMeta?.label ?? 'Integraciones'}
        </h1>
        {activeMeta?.hint ? (
          <p className="mt-1 text-sm text-gov-gray-600 dark:text-dark-muted">{activeMeta.hint}</p>
        ) : null}
      </header>

      {tab === 'edge' && <EdgeDevicesPageView embedded />}
      {tab === 'sensory' && <SensoryNodePageView embedded />}
      {tab === 'telegram' && <TelegramIntegrationPageView embedded />}
    </PageShell>
  );
}

export default function IntegracionesHubPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[40vh] items-center justify-center">
          <Loader2 className="animate-spin text-gov-blue-700" size={32} />
        </div>
      }
    >
      <IntegracionesHubContent />
    </Suspense>
  );
}
