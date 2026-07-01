'use client';

import { Suspense, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Loader2 } from 'lucide-react';
import { AdminHubShell } from '@/components/admin/AdminHubShell';
import PoliciesPageView from '@/components/policies/PoliciesPageView';
import SkillsHubView from '@/components/skills/SkillsHubView';
import { McpUnifiedView } from '@/components/mcp/McpUnifiedView';
import GenImagePageView from '@/components/gen/GenImagePageView';
import DuckDbPageView from '@/components/duckdb/DuckDbPageView';
import RuntimePageView from '@/components/runtime/RuntimePageView';

const TABS = [
  { id: 'reglas', label: 'Reglas base', hint: 'Policies de framework y wizard' },
  { id: 'skills', label: 'Skills', hint: 'Catálogo de capacidades' },
  { id: 'mcp', label: 'MCP', hint: 'Conectores y servidor MCP' },
  { id: 'imagenes', label: 'Imágenes', hint: 'Generación visual ComfyUI' },
  { id: 'duckdb', label: 'DuckDB', hint: 'Explorador de datos y grafos' },
  { id: 'runtime', label: 'Runtime', hint: 'Ajustes agent_config por vault' },
] as const;

type PlataformaTab = (typeof TABS)[number]['id'];

function parseTab(raw: string | null): PlataformaTab {
  const ids = new Set<string>(TABS.map((t) => t.id));
  if (raw && ids.has(raw)) return raw as PlataformaTab;
  return 'reglas';
}

function PlataformaHubContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [tab, setTab] = useState<PlataformaTab>(() => parseTab(searchParams.get('tab')));

  useEffect(() => {
    setTab(parseTab(searchParams.get('tab')));
  }, [searchParams]);

  const selectTab = (next: PlataformaTab) => {
    setTab(next);
    router.replace(`/plataforma?tab=${next}`, { scroll: false });
  };

  return (
    <AdminHubShell
      title="Plataforma"
      description="Reglas, capacidades, datos y runtime del framework."
      tabs={TABS}
      activeTabId={tab}
      onSelectTab={(id) => selectTab(parseTab(id))}
    >
      {tab === 'reglas' && <PoliciesPageView embedded />}
      {tab === 'skills' && <SkillsHubView embedded />}
      {tab === 'mcp' && <McpUnifiedView embedded />}
      {tab === 'imagenes' && <GenImagePageView embedded />}
      {tab === 'duckdb' && <DuckDbPageView embedded />}
      {tab === 'runtime' && <RuntimePageView embedded />}
    </AdminHubShell>
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
