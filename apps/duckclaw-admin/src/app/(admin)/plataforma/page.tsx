'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { PageShell } from '@/components/admin/PageShell';
import PoliciesPageView from '@/components/policies/PoliciesPageView';
import SkillsHubView from '@/components/skills/SkillsHubView';
import { McpUnifiedView } from '@/components/mcp/McpUnifiedView';
import GenImagePageView from '@/components/gen/GenImagePageView';
import DuckDbPageView from '@/components/duckdb/DuckDbPageView';
import RuntimePageView from '@/components/runtime/RuntimePageView';
import {
  PLATAFORMA_TABS,
  parsePlataformaTab,
  type PlataformaTabId,
} from '@/config/plataformaNav';

function PlataformaHubContent() {
  const searchParams = useSearchParams();
  const [tab, setTab] = useState<PlataformaTabId>(() => parsePlataformaTab(searchParams.get('tab')));

  useEffect(() => {
    setTab(parsePlataformaTab(searchParams.get('tab')));
  }, [searchParams]);

  const activeMeta = PLATAFORMA_TABS.find((t) => t.id === tab);

  return (
    <PageShell className="space-y-6">
      <header>
        <p className="text-xs font-black uppercase tracking-[0.2em] text-gov-blue-700 dark:text-dark-cyan">
          Plataforma
        </p>
        <h1 className="text-3xl font-black dark:text-dark-text">{activeMeta?.label ?? 'Plataforma'}</h1>
        {activeMeta?.hint ? (
          <p className="mt-1 max-w-3xl text-sm text-gov-gray-500 dark:text-dark-muted">{activeMeta.hint}</p>
        ) : null}
      </header>

      {tab === 'reglas' && <PoliciesPageView embedded />}
      {tab === 'skills' && <SkillsHubView embedded />}
      {tab === 'mcp' && <McpUnifiedView embedded />}
      {tab === 'imagenes' && <GenImagePageView embedded />}
      {tab === 'duckdb' && <DuckDbPageView embedded />}
      {tab === 'runtime' && <RuntimePageView embedded />}
    </PageShell>
  );
}

export default function PlataformaHubPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-[40vh] items-center justify-center">
          <Loader2 className="animate-spin text-gov-blue-700" size={32} />
        </div>
      }
    >
      <PlataformaHubContent />
    </Suspense>
  );
}
