'use client';

import { useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import SettingsSection from '@/components/settings/SettingsSection';
import { DuckDbVaultSelector } from '@/components/duckdb/DuckDbVaultSelector';
import { TableExplorer } from '@/components/duckdb/TableExplorer';
import { PGQVisualizer } from '@/components/duckdb/PGQVisualizer';
import { VectorExplorer } from '@/components/duckdb/VectorExplorer';
import { Database } from 'lucide-react';

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

  useEffect(() => {
    adminService.listVaults().then((r) => setVaults(r.vaults));
    adminService.getEnv().then((e) => setEnv(e.values));
  }, []);

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

      {tab === 'explorer' && <TableExplorer vaultPath={vaultPath} />}
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
