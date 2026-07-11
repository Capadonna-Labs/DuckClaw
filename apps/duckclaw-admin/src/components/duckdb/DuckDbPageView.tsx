'use client';

import { useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import { DuckDbVaultSelector } from '@/components/duckdb/DuckDbVaultSelector';
import { TableExplorer } from '@/components/duckdb/TableExplorer';
import { PGQVisualizer } from '@/components/duckdb/PGQVisualizer';
import { VectorExplorer } from '@/components/duckdb/VectorExplorer';
import { CodeDecisionsPanel } from '@/components/duckdb/CodeDecisionsPanel';
import ConfirmDangerModal from '@/components/admin/ConfirmDangerModal';
import { ViewChrome, type EmbeddedViewProps } from '@/components/admin/embeddedView';

type TabId = 'explorer' | 'pgq' | 'vector' | 'code';

const TABS: { id: TabId; label: string }[] = [
  { id: 'explorer', label: 'Tablas' },
  { id: 'pgq', label: 'PGQ' },
  { id: 'vector', label: 'Vectores' },
  { id: 'code', label: 'Code HITL' },
];

const TAB_HINTS: Record<TabId, string> = {
  explorer: 'Catálogo de tablas y SQL acotado (SELECT / INSERT vía gateway).',
  pgq: 'Grafo memory_nodes y memory_edges en la bóveda activa.',
  vector: 'Búsqueda en semantic_memory (VSS / léxico).',
  code: 'Propuestas de código pendientes de aprobación HITL.',
};

export default function DuckDbPageView({ embedded = false }: EmbeddedViewProps) {
  const [tab, setTab] = useState<TabId>('explorer');
  const [vaultPath, setVaultPath] = useState('');
  const [legacySchemas, setLegacySchemas] = useState<{ schema: string; table_count: number }[]>([]);
  const [legacyMainTables, setLegacyMainTables] = useState<{ schema: 'main'; table: string }[]>([]);
  const [selectedLegacy, setSelectedLegacy] = useState<string[]>([]);
  const [selectedLegacyMainTables, setSelectedLegacyMainTables] = useState<string[]>([]);
  const [confirmCleanup, setConfirmCleanup] = useState(false);
  const [cleanupBusy, setCleanupBusy] = useState(false);
  const [cleanupError, setCleanupError] = useState<string | null>(null);
  const [explorerRefresh, setExplorerRefresh] = useState(0);

  useEffect(() => {
    if (tab !== 'explorer') return;
    adminService
      .listDuckdbLegacySchemas(vaultPath || undefined)
      .then((r) => {
        setLegacySchemas(r.schemas ?? []);
        setLegacyMainTables(r.main_tables ?? []);
        setSelectedLegacy((prev) =>
          prev.filter((schema) => (r.schemas ?? []).some((item) => item.schema === schema))
        );
        setSelectedLegacyMainTables((prev) =>
          prev.filter((table) => (r.main_tables ?? []).some((item) => item.table === table))
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
        main_tables: selectedLegacyMainTables,
        vault_path: vaultPath || undefined,
        confirm: 'DROP_LEGACY_SCHEMAS',
      });
      setConfirmCleanup(false);
      setSelectedLegacy([]);
      setSelectedLegacyMainTables([]);
      setExplorerRefresh((v) => v + 1);
    } catch (e) {
      setCleanupError(e instanceof Error ? e.message : 'Error limpiando schemas legacy');
    } finally {
      setCleanupBusy(false);
    }
  };

  return (
    <ViewChrome embedded={embedded}>
      <div className="space-y-4">
        {!embedded && (
          <header className="border-b border-gov-gray-200 pb-4 dark:border-dark-border">
            <h1 className="text-2xl font-bold text-gov-gray-900 dark:text-dark-text">DuckDB</h1>
            <p className="mt-1 text-sm text-gov-gray-600 dark:text-dark-muted">
              Explorador de bóveda — solo lectura vía gateway salvo SQL acotado
            </p>
          </header>
        )}

        <div className="grid gap-4 lg:grid-cols-12">
          <aside className="space-y-4 lg:col-span-3">
            <section className="rounded-xl border border-gov-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
              <DuckDbVaultSelector value={vaultPath} onChange={setVaultPath} layout="stacked" />
            </section>

            <section className="rounded-xl border border-gov-gray-200 bg-gov-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
              <p className="text-sm font-semibold text-gov-gray-900 dark:text-dark-text">Memoria triple</p>
              <p className="mt-2 text-xs leading-relaxed text-gov-gray-600 dark:text-dark-muted">
                Cada tenant tiene su bóveda DuckDB: tablas SQL, grafo PGQ y vectores VSS. El gateway
                expone lecturas; las mutaciones estructuradas van por db-writer.
              </p>
            </section>

            <section className="rounded-xl border border-gov-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
              <p className="text-xs font-medium text-gov-gray-500 dark:text-dark-muted">Sección activa</p>
              <p className="mt-1 text-sm text-gov-gray-800 dark:text-dark-text">{TAB_HINTS[tab]}</p>
            </section>
          </aside>

          <div className="space-y-4 lg:col-span-9">
            <div
              className="flex flex-wrap gap-1 border-b border-gov-gray-200 dark:border-dark-border"
              role="tablist"
              aria-label="Secciones DuckDB"
            >
              {TABS.map((t) => {
                const selected = tab === t.id;
                return (
                  <button
                    key={t.id}
                    type="button"
                    role="tab"
                    aria-selected={selected}
                    onClick={() => setTab(t.id)}
                    className={`-mb-px border-b-2 px-4 py-2.5 text-sm font-semibold transition-colors ${
                      selected
                        ? 'border-gov-blue-600 text-gov-blue-800 dark:border-dark-cyan dark:text-dark-cyan'
                        : 'border-transparent text-gov-gray-500 hover:text-gov-gray-800 dark:hover:text-dark-text'
                    }`}
                  >
                    {t.label}
                  </button>
                );
              })}
            </div>

            {tab === 'explorer' && (
              <div className="space-y-4">
                {(legacySchemas.length > 0 || legacyMainTables.length > 0) && (
                  <section className="rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-800 dark:bg-amber-950/25">
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                      <div>
                        <h2 className="font-semibold text-amber-950 dark:text-amber-100">
                          Schemas legacy detectados
                        </h2>
                        <p className="mt-1 text-xs text-amber-900 dark:text-amber-100/80">
                          Selecciona y elimina solo lo que no pertenezca a tu perfil.
                        </p>
                        <div className="mt-3 flex flex-wrap gap-2">
                          {legacySchemas.map((item) => {
                            const checked = selectedLegacy.includes(item.schema);
                            return (
                              <label
                                key={item.schema}
                                className="inline-flex items-center gap-2 rounded-lg border border-amber-200 bg-white px-3 py-2 font-mono text-xs dark:border-amber-800 dark:bg-dark-bg"
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
                        {legacyMainTables.length > 0 && (
                          <>
                            <p className="mt-4 text-xs font-medium text-amber-950 dark:text-amber-100">
                              Tablas legacy en main
                            </p>
                            <div className="mt-2 flex flex-wrap gap-2">
                              {legacyMainTables.map((item) => {
                                const checked = selectedLegacyMainTables.includes(item.table);
                                return (
                                  <label
                                    key={item.table}
                                    className="inline-flex items-center gap-2 rounded-lg border border-amber-200 bg-white px-3 py-2 font-mono text-xs dark:border-amber-800 dark:bg-dark-bg"
                                  >
                                    <input
                                      type="checkbox"
                                      checked={checked}
                                      onChange={(e) =>
                                        setSelectedLegacyMainTables((prev) =>
                                          e.target.checked
                                            ? [...prev, item.table]
                                            : prev.filter((table) => table !== item.table)
                                        )
                                      }
                                    />
                                    main.{item.table}
                                  </label>
                                );
                              })}
                            </div>
                          </>
                        )}
                      </div>
                      <button
                        type="button"
                        disabled={selectedLegacy.length === 0 && selectedLegacyMainTables.length === 0}
                        onClick={() => setConfirmCleanup(true)}
                        className="rounded-lg bg-red-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                      >
                        Eliminar seleccionados
                      </button>
                    </div>
                    {cleanupError && (
                      <p className="mt-3 text-red-700 dark:text-red-300">{cleanupError}</p>
                    )}
                  </section>
                )}
                <TableExplorer vaultPath={vaultPath} refreshKey={explorerRefresh} />
              </div>
            )}
            {tab === 'pgq' && <PGQVisualizer vaultPath={vaultPath} />}
            {tab === 'vector' && <VectorExplorer vaultPath={vaultPath} />}
            {tab === 'code' && <CodeDecisionsPanel vaultPath={vaultPath} />}
          </div>
        </div>

        <ConfirmDangerModal
          isOpen={confirmCleanup}
          title="Eliminar schemas legacy"
          description="Se ejecutará DROP SCHEMA CASCADE sobre la bóveda seleccionada."
          confirmLabel="Eliminar schemas"
          isLoading={cleanupBusy}
          details={[
            { label: 'Confirmación', value: 'DROP_LEGACY_SCHEMAS' },
            { label: 'Schemas', value: selectedLegacy.join(', ') || 'Ninguno' },
            { label: 'Tablas main', value: selectedLegacyMainTables.join(', ') || 'Ninguna' },
            { label: 'Vault', value: vaultPath || 'Bóveda activa del usuario' },
          ]}
          onCancel={() => setConfirmCleanup(false)}
          onConfirm={cleanupLegacySchemas}
        />
      </div>
    </ViewChrome>
  );
}
