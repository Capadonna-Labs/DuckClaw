'use client';

import { useEffect, useState } from 'react';
import { Database } from 'lucide-react';
import { adminService } from '@/services/adminService';

type Props = {
  value: string;
  onChange: (path: string) => void;
};

type VaultOption = {
  path: string;
  scope: string;
  active?: boolean;
};

export function DuckDbVaultSelector({ value, onChange }: Props) {
  const [vaults, setVaults] = useState<VaultOption[]>([]);

  useEffect(() => {
    adminService.listVaults().then((r) => setVaults(r.vaults));
  }, []);

  useEffect(() => {
    if (!value && vaults.length > 0) {
      onChange(vaults.find((v) => v.active)?.path || vaults[0].path);
    }
  }, [vaults, value, onChange]);

  return (
    <label className="flex items-center gap-2 text-sm">
      <Database size={16} className="text-gov-blue-600 dark:text-dark-cyan shrink-0" />
      <span className="text-gov-gray-500 dark:text-dark-muted shrink-0">Bóveda</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="flex-1 min-w-0 max-w-xl px-3 py-2 rounded-xl border dark:border-dark-border dark:bg-dark-bg font-mono text-xs"
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
