'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { RefreshCw } from 'lucide-react';
import ConfirmDangerModal from '@/components/admin/ConfirmDangerModal';
import { ViewChrome, type EmbeddedViewProps } from '@/components/admin/embeddedView';
import { SkillCreateForm } from '@/components/skills/SkillCreateForm';
import { SkillInventory } from '@/components/skills/SkillInventory';
import { PlatformSkillsPanel } from '@/components/skills/PlatformSkillsPanel';
import { useSkillsCatalog } from '@/components/skills/useSkillsCatalog';
import { useDeveloperMode } from '@/hooks/useDeveloperMode';
import { readDeveloperMode } from '@/lib/developerMode';
import { adminService, type SkillCatalogItem } from '@/services/adminService';
import { useAuthStore } from '@/store/authStore';

const BASE_TABS = [
  { id: 'catalog', label: 'Catálogo' },
  { id: 'platform', label: 'Framework' },
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
      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div
            className="flex flex-wrap gap-1 border-b border-gov-gray-200 dark:border-dark-border"
            role="tablist"
            aria-label="Secciones de skills"
          >
            {visibleTabs.map((item) => {
              const selected = tab === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  role="tab"
                  aria-selected={selected}
                  onClick={() => selectTab(item.id)}
                  className={`border-b-2 px-4 py-2.5 text-sm font-semibold transition-colors -mb-px ${
                    selected
                      ? 'border-gov-blue-600 text-gov-blue-800 dark:border-dark-cyan dark:text-dark-cyan'
                      : 'border-transparent text-gov-gray-500 hover:text-gov-gray-800 dark:hover:text-dark-text'
                  }`}
                >
                  {item.label}
                </button>
              );
            })}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <label className="inline-flex cursor-pointer items-center gap-2 rounded-lg border border-gov-gray-200 px-3 py-1.5 text-xs dark:border-dark-border">
              <input
                type="checkbox"
                checked={developerMode}
                onChange={(e) => setDeveloperMode(e.target.checked)}
                className="rounded"
              />
              <span className="font-medium text-gov-gray-700 dark:text-dark-muted">Desarrollador</span>
            </label>
            <button
              type="button"
              onClick={refresh}
              className="inline-flex items-center gap-2 rounded-lg border border-gov-gray-200 px-3 py-1.5 text-xs font-semibold text-gov-gray-700 dark:border-dark-border dark:text-dark-muted"
            >
              <RefreshCw size={14} />
              Refrescar
            </button>
          </div>
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}
        {deleteError && <p className="text-sm text-red-600">{deleteError}</p>}

        {tab === 'catalog' && (
          <div className="grid gap-4 lg:grid-cols-12">
            <div className="space-y-4 lg:col-span-8">
              <SkillInventory
                title="Catálogo global"
                subtitle="main.admin_skills"
                items={globalSkills}
                canDelete={canWrite}
                onHardDelete={setPendingHardDelete}
                emptyHint={
                  developerMode
                    ? 'Sin filas en catálogo. Crea metadata en la pestaña Crear.'
                    : 'Activa modo desarrollador para registrar skills custom en DuckDB.'
                }
                onCreateClick={developerMode ? () => selectTab('create') : undefined}
              />
              <SkillInventory
                title="Locales por agente"
                subtitle="skills/*.py en el snapshot del worker"
                items={localSkills}
                showWorker
                emptyHint="Archivos en el editor del agente → pestaña Herramientas / archivos skills/."
              />
            </div>
            <aside className="lg:col-span-4">
              <section className="rounded-xl border border-gov-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
                <p className="text-sm font-semibold text-gov-gray-900 dark:text-dark-text">Resumen</p>
                <dl className="mt-3 space-y-2 text-sm">
                  <div className="flex justify-between gap-2">
                    <dt className="text-gov-gray-500 dark:text-dark-muted">Globales</dt>
                    <dd className="font-mono font-semibold">{globalSkills.length}</dd>
                  </div>
                  <div className="flex justify-between gap-2">
                    <dt className="text-gov-gray-500 dark:text-dark-muted">Locales</dt>
                    <dd className="font-mono font-semibold">{localSkills.length}</dd>
                  </div>
                </dl>
              </section>
            </aside>
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
        description="Borra la fila en main.admin_skills y sus enlaces en admin_worker_skills."
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
