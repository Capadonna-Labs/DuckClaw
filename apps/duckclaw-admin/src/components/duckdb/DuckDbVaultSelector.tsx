'use client';

import { useEffect, useState } from 'react';
import { Database } from 'lucide-react';
import { adminService } from '@/services/adminService';

type Props = {
  value: string;
  onChange: (path: string) => void;
  layout?: 'inline' | 'stacked';
};

type VaultOption = {
  path: string;
  scope: string;
  active?: boolean;
};

export function DuckDbVaultSelector({ value, onChange, layout = 'stacked' }: Props) {
  const [vaults, setVaults] = useState<VaultOption[]>([]);

  useEffect(() => {
    adminService.listVaults().then((r) => setVaults(r.vaults));
  }, []);

  useEffect(() => {
    if (!value && vaults.length > 0) {
      onChange(vaults.find((v) => v.active)?.path || vaults[0].path);
    }
  }, [vaults, value, onChange]);

  if (layout === 'inline') {
    return (
      <label className="flex items-center gap-2 text-sm">
        <Database size={16} className="shrink-0 text-gov-blue-600 dark:text-dark-cyan" />
        <span className="shrink-0 text-gov-gray-500 dark:text-dark-muted">Bóveda</span>
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="min-w-0 max-w-xl flex-1 rounded-lg border px-3 py-2 font-mono text-xs dark:border-dark-border dark:bg-dark-bg"
        >
          {vaults.length === 0 && <option value="">(sin bóvedas)</option>}
          {vaults.map((v) => (
            <option key={v.path} value={v.path}>
              [{v.scope}{v.active ? ' activa' : ''}] {v.path}
            </option>
          ))}
        </select>
      </label>
    );
  }

  return (
    <label className="block text-sm">
      <span className="inline-flex items-center gap-1.5 font-medium text-gov-gray-800 dark:text-dark-text">
        <Database size={14} className="text-gov-blue-600 dark:text-dark-cyan" />
        Bóveda
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1.5 w-full rounded-lg border border-gov-gray-200 bg-white px-3 py-2 font-mono text-xs dark:border-dark-border dark:bg-dark-bg"
      >
        {vaults.length === 0 && <option value="">(sin bóvedas)</option>}
        {vaults.map((v) => (
          <option key={v.path} value={v.path}>
            [{v.scope}{v.active ? ' activa' : ''}] {v.path}
          </option>
        ))}
      </select>
    </label>
  );
}
