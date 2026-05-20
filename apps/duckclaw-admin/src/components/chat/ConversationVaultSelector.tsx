'use client';

import { useEffect, useState } from 'react';
import { Database, Loader2 } from 'lucide-react';
import { adminService } from '@/services/adminService';

export type VaultOption = { path: string; scope: string; vault_id?: string; label?: string };

type Props = {
  chatId: string;
  tenantId?: string;
  value: string;
  effectivePath?: string;
  scope?: string;
  options?: VaultOption[];
  onChange: (path: string) => void;
  onUpdated?: () => void;
  disabled?: boolean;
  compact?: boolean;
};

export function ConversationVaultSelector({
  chatId,
  tenantId = 'default',
  value,
  effectivePath,
  scope,
  options: optionsProp,
  onChange,
  onUpdated,
  disabled,
  compact,
}: Props) {
  const [options, setOptions] = useState<VaultOption[]>(optionsProp ?? []);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (optionsProp?.length) {
      setOptions(optionsProp);
      return;
    }
    adminService.listVaults().then((r) => setOptions(r.vaults));
  }, [optionsProp]);

  const persist = async (path: string) => {
    if (!chatId || disabled || pending) return;
    setError(null);
    setPending(true);
    try {
      await adminService.setPlaygroundVault({
        chat_id: chatId,
        tenant_id: tenantId,
        vault_db_path: path,
      });
      onChange(path);
      onUpdated?.();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error al guardar bóveda');
    } finally {
      setPending(false);
    }
  };

  const labelCls = compact ? 'text-[10px]' : 'text-xs';

  return (
    <div className={`space-y-1 ${compact ? '' : 'min-w-0'}`}>
      <label className={`flex items-center gap-2 ${labelCls}`}>
        <Database
          size={compact ? 14 : 16}
          className="text-gov-blue-600 dark:text-dark-cyan shrink-0"
        />
        <span className="text-gov-gray-500 dark:text-dark-muted shrink-0">Bóveda</span>
        <select
          value={value}
          disabled={disabled || pending || !options.length}
          onChange={(e) => void persist(e.target.value)}
          className={`flex-1 min-w-0 border rounded-lg dark:border-dark-border dark:bg-dark-bg font-mono ${
            compact ? 'text-[10px] px-1.5 py-1 max-w-[180px]' : 'text-xs px-2 py-1.5 max-w-[240px]'
          }`}
          aria-label="Bóveda DuckDB de la conversación"
        >
          {options.length === 0 && <option value="">(sin bóvedas)</option>}
          {options.map((v) => (
            <option key={v.path} value={v.path}>
              [{v.scope}] {v.path}
            </option>
          ))}
        </select>
        {pending && <Loader2 size={14} className="animate-spin text-gov-gray-400 shrink-0" />}
      </label>
      {!compact && effectivePath && (
        <p className="text-[10px] text-gov-gray-500 font-mono truncate" title={effectivePath}>
          Activa: {effectivePath}
          {scope === 'chat' ? ' (por conversación)' : ''}
        </p>
      )}
      {error && <p className="text-[10px] text-red-600">{error}</p>}
    </div>
  );
}
