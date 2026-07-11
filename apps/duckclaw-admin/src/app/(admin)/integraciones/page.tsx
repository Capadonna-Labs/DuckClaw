'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { AdminHubShell } from '@/components/admin/AdminHubShell';
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
  const [tab, setTab] = useState<IntegracionesTabId>(() => parseIntegracionesTab(searchParams.get('tab')));

  useEffect(() => {
    setTab(parseIntegracionesTab(searchParams.get('tab')));
  }, [searchParams]);

  const activeLabel = INTEGRACIONES_TABS.find((t) => t.id === tab)?.label ?? 'Integraciones';

  return (
    <AdminHubShell title={activeLabel} description="Canales y nodos periféricos conectados a DuckClaw.">
      {tab === 'edge' && <EdgeDevicesPageView embedded />}
      {tab === 'sensory' && <SensoryNodePageView embedded />}
      {tab === 'telegram' && <TelegramIntegrationPageView embedded />}
    </AdminHubShell>
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
