'use client';

import { useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import SettingsSection from '@/components/settings/SettingsSection';
import { Database } from 'lucide-react';

export default function DuckDbPage() {
  const [vaults, setVaults] = useState<{ path: string; scope: string }[]>([]);
  const [env, setEnv] = useState<Record<string, string>>({});

  useEffect(() => {
    adminService.listVaults().then((r) => setVaults(r.vaults));
    adminService.getEnv().then((e) => setEnv(e.values));
  }, []);

  const duckKeys = Object.entries(env).filter(([k]) => k.includes('DUCK') || k.includes('DB'));

  return (
    <div className="space-y-8">
      <h1 className="text-3xl font-black dark:text-dark-text">DuckDB</h1>
      <SettingsSection titulo="Bóvedas" icono={<Database size={22} />}>
        <ul className="text-sm font-mono space-y-1 max-h-64 overflow-y-auto">
          {vaults.map((v) => (
            <li key={v.path} className="p-2 rounded-lg bg-gov-gray-50 dark:bg-dark-bg">
              [{v.scope}] {v.path}
            </li>
          ))}
        </ul>
      </SettingsSection>
      <SettingsSection titulo="Variables .env" descripcion="Valores enmascarados">
        <dl className="text-sm space-y-2">
          {duckKeys.map(([k, v]) => (
            <motionEnvRow key={k} k={k} v={v} />
          ))}
        </dl>
      </SettingsSection>
    </div>
  );
}

function motionEnvRow({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex gap-4">
      <dt className="font-mono text-gov-gray-500 w-48 shrink-0">{k}</dt>
      <dd className="font-mono">{v}</dd>
    </div>
  );
}
