'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { RefreshCw } from 'lucide-react';
import { ViewChrome, type EmbeddedViewProps } from '@/components/admin/embeddedView';
import { SkillCreateForm } from '@/components/skills/SkillCreateForm';
import { SkillInventory } from '@/components/skills/SkillInventory';
import { SkillSummary } from '@/components/skills/SkillSummary';
import { SkillsConceptPanel } from '@/components/skills/SkillsConceptPanel';
import { PlatformSkillsPanel } from '@/components/skills/PlatformSkillsPanel';
import { useSkillsCatalog } from '@/components/skills/useSkillsCatalog';

const TABS = [
  { id: 'catalog', label: 'Catálogo DB' },
  { id: 'platform', label: 'Plataforma' },
  { id: 'create', label: 'Crear' },
] as const;

type SkillsTab = (typeof TABS)[number]['id'];

function parseSkillsTab(raw: string | null): SkillsTab {
  if (raw === 'platform' || raw === 'create' || raw === 'catalog') return raw;
  if (raw === 'global' || raw === 'local' || raw === 'summary') return 'catalog';
  if (raw === 'new') return 'create';
  return 'catalog';
}

export default function SkillsHubView({ embedded = false }: EmbeddedViewProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [tab, setTab] = useState<SkillsTab>(() => parseSkillsTab(searchParams.get('skillsTab')));
  const { globalSkills, localSkills, error, loadSkills } = useSkillsCatalog();

  useEffect(() => {
    setTab(parseSkillsTab(searchParams.get('skillsTab')));
  }, [searchParams]);

  const selectTab = useCallback(
    (next: SkillsTab) => {
      setTab(next);
      if (embedded) {
        const params = new URLSearchParams(searchParams.toString());
        params.set('tab', 'skills');
        params.set('skillsTab', next);
        router.replace(`/plataforma?${params.toString()}`, { scroll: false });
      }
    },
    [embedded, router, searchParams]
  );

  const refresh = useCallback(() => {
    void loadSkills().catch(() => undefined);
  }, [loadSkills]);

  const showEmptyGlobalHint = useMemo(() => globalSkills.length === 0, [globalSkills.length]);

  return (
    <ViewChrome embedded={embedded}>
      {!embedded && (
        <header>
          <h1 className="text-3xl font-black dark:text-dark-text">Skills</h1>
          <p className="mt-1 max-w-2xl text-sm text-gov-gray-500 dark:text-dark-muted">
            Capacidades que el agente expone al LLM como herramientas. Inventario, creación y skills del
            framework en un solo lugar.
          </p>
        </header>
      )}

      <div className="space-y-6">
        <SkillsConceptPanel defaultOpen={showEmptyGlobalHint} />

        <SkillSummary
          globalCount={globalSkills.length}
          localCount={localSkills.length}
          onCreateClick={() => selectTab('create')}
        />

        <div className="flex flex-wrap items-center justify-between gap-3">
          <nav className="flex flex-wrap gap-1 rounded-xl border border-gov-gray-200 bg-gov-gray-50 p-1 dark:border-dark-border dark:bg-dark-bg">
            {TABS.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => selectTab(item.id)}
                className={`rounded-lg px-3 py-1.5 text-xs font-bold transition-colors ${
                  tab === item.id
                    ? 'bg-white text-gov-blue-800 shadow-sm dark:bg-dark-surface dark:text-dark-cyan'
                    : 'text-gov-gray-600 hover:text-gov-gray-900 dark:text-dark-muted dark:hover:text-dark-text'
                }`}
              >
                {item.label}
              </button>
            ))}
          </nav>
          <button
            type="button"
            onClick={refresh}
            className="inline-flex items-center gap-2 rounded-xl border border-gov-gray-200 px-3 py-2 text-xs font-bold text-gov-gray-700 dark:border-dark-border dark:text-dark-muted"
          >
            <RefreshCw size={14} />
            Refrescar
          </button>
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        {tab === 'catalog' && (
          <div className="space-y-6">
            <SkillInventory
              title="Catálogo global"
              subtitle="Filas en main.admin_skills — reutilizables entre agentes."
              items={globalSkills}
              emptyHint="Crea una skill en la pestaña Crear, implementa el bridge Python y actívala en el manifest del agente."
              onCreateClick={() => selectTab('create')}
            />
            <SkillInventory
              title="Skills locales por agente"
              subtitle="Archivos skills/*.py dentro del snapshot de cada worker."
              items={localSkills}
              showWorker
              emptyHint="Sube o edita archivos .py en el bundle del agente (editor → archivos skills/)."
            />
          </div>
        )}

        {tab === 'platform' && <PlatformSkillsPanel />}

        {tab === 'create' && (
          <SkillCreateForm
            onCreated={async () => {
              await loadSkills();
              selectTab('catalog');
            }}
          />
        )}
      </div>
    </ViewChrome>
  );
}
