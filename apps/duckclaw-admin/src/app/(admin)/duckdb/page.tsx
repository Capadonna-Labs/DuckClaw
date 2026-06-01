'use client';

import { useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import SettingsSection from '@/components/settings/SettingsSection';
import { DuckDbVaultSelector } from '@/components/duckdb/DuckDbVaultSelector';
import { TableExplorer } from '@/components/duckdb/TableExplorer';
import { PGQVisualizer } from '@/components/duckdb/PGQVisualizer';
import { VectorExplorer } from '@/components/duckdb/VectorExplorer';
import { Database } from 'lucide-react';
import ConfirmDangerModal from '@/components/admin/ConfirmDangerModal';

type TabId = 'explorer' | 'pgq' | 'vector' | 'overview';

const TABS: { id: TabId; label: string }[] = [
  { id: 'explorer', label: 'Data Explorer' },
  { id: 'pgq', label: 'PGQ Graph' },
  { id: 'vector', label: 'Vector Memory' },
  { id: 'overview', label: 'Overview' },
];

export default function DuckDbPage() {
  const [tab, setTab] = useState<TabId>('explorer');
  const [vaultPath, setVaultPath] = useState('');
  const [vaults, setVaults] = useState<{ path: string; scope: string }[]>([]);
  const [env, setEnv] = useState<Record<string, string>>({});
  const [legacySchemas, setLegacySchemas] = useState<{ schema: string; table_count: number }[]>([]);
  const [selectedLegacy, setSelectedLegacy] = useState<string[]>([]);
  const [confirmCleanup, setConfirmCleanup] = useState(false);
  const [cleanupBusy, setCleanupBusy] = useState(false);
  const [cleanupError, setCleanupError] = useState<string | null>(null);
  const [explorerRefresh, setExplorerRefresh] = useState(0);

  useEffect(() => {
    adminService.listVaults().then((r) => setVaults(r.vaults));
    adminService.getEnv().then((e) => setEnv(e.values));
  }, []);

  useEffect(() => {
    if (tab !== 'explorer') return;
    adminService
      .listDuckdbLegacySchemas(vaultPath || undefined)
      .then((r) => {
        setLegacySchemas(r.schemas ?? []);
        setSelectedLegacy((prev) =>
          prev.filter((schema) => (r.schemas ?? []).some((item) => item.schema === schema))
        );
      })
      .catch((e) => setCleanupError(e instanceof Error ? e.message : 'Error revisando schemas legacy'));
  }, [tab, vaultPath, explorerRefresh]);

  const cleanupLegacySchemas = async () => {
    setCleanupBusy(true);
    setCleanupError(null);
    try {
      await adminService.dropDuckdbLegacySchemas({
        schemas: selectedLegacy,
        vault_path: vaultPath || undefined,
        confirm: 'DROP_LEGACY_SCHEMAS',
      });
      setConfirmCleanup(false);
      setSelectedLegacy([]);
      setExplorerRefresh((v) => v + 1);
    } catch (e) {
      setCleanupError(e instanceof Error ? e.message : 'Error limpiando schemas legacy');
    } finally {
      setCleanupBusy(false);
    }
  };

  const duckKeys = Object.entries(env).filter(([k]) => k.includes('DUCK') || k.includes('DB'));

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">DuckDB</h1>
        <p className="text-sm text-gov-gray-500 dark:text-dark-muted mt-1">
          Explorador tabular, grafo PGQ y memoria vectorial (solo lectura vía gateway)
        </p>
      </header>

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
      </div>

      {tab !== 'overview' && (
        <DuckDbVaultSelector value={vaultPath} onChange={setVaultPath} />
      )}

      {tab === 'explorer' && (
        <div className="space-y-4">
          {legacySchemas.length > 0 && (
            <section className="rounded-2xl border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-800 dark:bg-amber-950/25">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div>
                  <h2 className="font-black text-amber-950 dark:text-amber-100">
                    Schemas legacy detectados
                  </h2>
                  <p className="mt-1 text-amber-900 dark:text-amber-100/80">
                    No se ocultan. Si no pertenecen a tu perfil, selecciónalos y elimínalos con
                    confirmación explícita.
                  </p>
                  <div className="mt-3 flex flex-wrap gap-2">
                    {legacySchemas.map((item) => {
                      const checked = selectedLegacy.includes(item.schema);
                      return (
                        <label
                          key={item.schema}
                          className="inline-flex items-center gap-2 rounded-xl border border-amber-200 bg-white px-3 py-2 font-mono text-xs dark:border-amber-800 dark:bg-dark-bg"
                        >
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={(e) =>
                              setSelectedLegacy((prev) =>
                                e.target.checked
                                  ? [...prev, item.schema]
                                  : prev.filter((schema) => schema !== item.schema)
                              )
                            }
                          />
                          {item.schema} ({item.table_count})
                        </label>
                      );
                    })}
                  </div>
                </div>
                <button
                  type="button"
                  disabled={selectedLegacy.length === 0}
                  onClick={() => setConfirmCleanup(true)}
                  className="rounded-xl bg-red-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                >
                  Eliminar seleccionados
                </button>
              </div>
              {cleanupError && <p className="mt-3 text-red-700 dark:text-red-300">{cleanupError}</p>}
            </section>
          )}
          <TableExplorer vaultPath={vaultPath} refreshKey={explorerRefresh} />
        </div>
      )}
      {tab === 'pgq' && <PGQVisualizer vaultPath={vaultPath} />}
      {tab === 'vector' && <VectorExplorer vaultPath={vaultPath} />}

      {tab === 'overview' && (
        <div className="space-y-8">
          <SettingsSection titulo="Bóvedas" icono={<Database size={22} />}>
            <ul className="text-sm font-mono space-y-1 max-h-64 overflow-y-auto">
              {vaults.map((v) => (
                <li key={v.path} className="p-2 rounded-lg bg-gov-gray-50 dark:bg-dark-bg">
                  [{v.scope}] {v.path}
                </li>
              ))}
            </ul>
          </SettingsSection>
          <SettingsSection
            titulo="Variables .env"
            descripcion="Valores enmascarados"
            icono={<Database size={22} />}
          >
            <dl className="text-sm space-y-2">
              {duckKeys.map(([k, v]) => (
                <EnvRow key={k} k={k} v={v} />
              ))}
            </dl>
          </SettingsSection>
        </div>
      )}
      <ConfirmDangerModal
        isOpen={confirmCleanup}
        title="Eliminar schemas legacy"
        description="Se ejecutará DROP SCHEMA CASCADE sobre la bóveda seleccionada."
        confirmLabel="Eliminar schemas"
        isLoading={cleanupBusy}
        details={[
          { label: 'Confirmación', value: 'DROP_LEGACY_SCHEMAS' },
          { label: 'Schemas', value: selectedLegacy.join(', ') || 'Ninguno' },
          { label: 'Vault', value: vaultPath || 'Bóveda activa del usuario' },
        ]}
        onCancel={() => setConfirmCleanup(false)}
        onConfirm={cleanupLegacySchemas}
      />
    </div>
  );
}

function EnvRow({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-4">
      <dt className="font-mono text-gov-gray-500 w-48 shrink-0">{k}</dt>
      <dd className="font-mono">{v}</dd>
    </div>
  );
}
