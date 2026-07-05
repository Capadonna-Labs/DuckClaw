'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { RefreshCw } from 'lucide-react';
import ConfirmDangerModal from '@/components/admin/ConfirmDangerModal';
import { ViewChrome, type EmbeddedViewProps } from '@/components/admin/embeddedView';
import { SkillCreateForm } from '@/components/skills/SkillCreateForm';
import { SkillInventory } from '@/components/skills/SkillInventory';
import { SkillSummary } from '@/components/skills/SkillSummary';
import { SkillsConceptPanel } from '@/components/skills/SkillsConceptPanel';
import { PlatformSkillsPanel } from '@/components/skills/PlatformSkillsPanel';
import { useSkillsCatalog } from '@/components/skills/useSkillsCatalog';
import { useDeveloperMode } from '@/hooks/useDeveloperMode';
import { readDeveloperMode } from '@/lib/developerMode';
import { adminService, type SkillCatalogItem } from '@/services/adminService';
import { useAuthStore } from '@/store/authStore';

const BASE_TABS = [
  { id: 'catalog', label: 'Catálogo DB' },
  { id: 'platform', label: 'Plataforma' },
] as const;

const CREATE_TAB = { id: 'create', label: 'Crear' } as const;

type SkillsTab = 'catalog' | 'platform' | 'create';

function parseSkillsTab(raw: string | null, developerMode: boolean): SkillsTab {
  if (raw === 'create') return developerMode ? 'create' : 'catalog';
  if (raw === 'platform' || raw === 'catalog') return raw;
  if (raw === 'global' || raw === 'local' || raw === 'summary') return 'catalog';
  if (raw === 'new') return developerMode ? 'create' : 'catalog';
  return 'catalog';
}

export default function SkillsHubView({ embedded = false }: EmbeddedViewProps) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { usuario } = useAuthStore();
  const { developerMode, setDeveloperMode } = useDeveloperMode();
  const canWrite = usuario?.rol === 'admin';
  const [tab, setTab] = useState<SkillsTab>(() =>
    parseSkillsTab(searchParams.get('skillsTab'), readDeveloperMode())
  );
  const [pendingHardDelete, setPendingHardDelete] = useState<SkillCatalogItem | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const { globalSkills, localSkills, error, loadSkills } = useSkillsCatalog();

  useEffect(() => {
    setTab(parseSkillsTab(searchParams.get('skillsTab'), developerMode));
  }, [searchParams, developerMode]);

  useEffect(() => {
    if (!developerMode && tab === 'create') {
      setTab('catalog');
    }
  }, [developerMode, tab]);

  const visibleTabs = developerMode ? [...BASE_TABS, CREATE_TAB] : [...BASE_TABS];

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

  const confirmHardDelete = async () => {
    if (!pendingHardDelete || !canWrite) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await adminService.hardDeleteSkill(pendingHardDelete.id);
      setPendingHardDelete(null);
      await loadSkills();
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : 'No se pudo eliminar la skill');
    } finally {
      setDeleting(false);
    }
  };

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
          onCreateClick={developerMode ? () => selectTab('create') : undefined}
        />

        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap items-center gap-3">
            <nav className="flex flex-wrap gap-1 rounded-xl border border-gov-gray-200 bg-gov-gray-50 p-1 dark:border-dark-border dark:bg-dark-bg">
              {visibleTabs.map((item) => (
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
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-xl border border-gov-gray-200 px-3 py-2 text-xs dark:border-dark-border">
              <input
                type="checkbox"
                checked={developerMode}
                onChange={(e) => setDeveloperMode(e.target.checked)}
                className="rounded"
              />
              <span className="font-semibold text-gov-gray-700 dark:text-dark-muted">Modo desarrollador</span>
            </label>
          </div>
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
        {deleteError && <p className="text-sm text-red-600">{deleteError}</p>}

        {tab === 'catalog' && (
          <div className="space-y-6">
            <SkillInventory
              title="Catálogo global"
              subtitle="Filas en main.admin_skills — reutilizables entre agentes."
              items={globalSkills}
              canDelete={canWrite}
              onHardDelete={setPendingHardDelete}
              emptyHint={
                developerMode
                  ? 'Crea metadata en la pestaña Crear, implementa el bridge Python y actívala en el manifest del agente.'
                  : 'Los agentes ya incluyen capacidades de plataforma (datos, documentos, informes). Activa «Modo desarrollador» solo si vas a registrar skills custom en DuckDB.'
              }
              onCreateClick={developerMode ? () => selectTab('create') : undefined}
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

        {tab === 'create' && developerMode && (
          <SkillCreateForm
            onCreated={async () => {
              await loadSkills();
              selectTab('catalog');
            }}
          />
        )}
      </div>

      <ConfirmDangerModal
        isOpen={!!pendingHardDelete}
        title="Eliminar skill definitivamente"
        description="Borra la fila en main.admin_skills y sus enlaces en admin_worker_skills. No elimina código Python en disco salvo que lo hayas subido aparte."
        confirmLabel="Sí, eliminar definitivamente"
        isLoading={deleting}
        details={
          pendingHardDelete
            ? [
                { label: 'Nombre', value: pendingHardDelete.id },
                { label: 'Implementación', value: pendingHardDelete.path },
                { label: 'Alcance', value: 'Catálogo global (tenant)' },
              ]
            : []
        }
        onCancel={() => !deleting && setPendingHardDelete(null)}
        onConfirm={() => void confirmHardDelete()}
      />
    </ViewChrome>
  );
}
