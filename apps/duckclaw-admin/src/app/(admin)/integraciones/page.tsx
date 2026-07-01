'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { AdminHubShell } from '@/components/admin/AdminHubShell';
import EdgeDevicesPageView from '@/components/integrations/EdgeDevicesPageView';
import SensoryNodePageView from '@/components/integrations/SensoryNodePageView';
import TelegramIntegrationPageView from '@/components/integrations/TelegramIntegrationPageView';

const TABS = [
  { id: 'edge', label: 'Edge devices', hint: 'Telemetría libedgecore' },
  { id: 'sensory', label: 'Sensory node', hint: 'STT/TTS en Mac mini' },
  { id: 'telegram', label: 'Telegram', hint: 'Canal opcional de mensajería' },
] as const;

type IntegracionesTab = (typeof TABS)[number]['id'];

function parseTab(raw: string | null): IntegracionesTab {
  if (raw === 'edge' || raw === 'sensory' || raw === 'telegram') return raw;
  return 'telegram';
}

function IntegracionesHubContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [tab, setTab] = useState<IntegracionesTab>(() => parseTab(searchParams.get('tab')));

  useEffect(() => {
    setTab(parseTab(searchParams.get('tab')));
  }, [searchParams]);

  const selectTab = (next: IntegracionesTab) => {
    setTab(next);
    router.replace(`/integraciones?tab=${next}`, { scroll: false });
  };

  return (
    <AdminHubShell
      title="Integraciones"
      description="Canales y nodos periféricos conectados a DuckClaw."
      tabs={TABS}
      activeTabId={tab}
      onSelectTab={(id) => selectTab(parseTab(id))}
    >
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
