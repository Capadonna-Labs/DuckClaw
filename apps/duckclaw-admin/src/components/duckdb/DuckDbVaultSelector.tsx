'use client';

import { useEffect, useMemo, useState } from 'react';
import { Database, Plus } from 'lucide-react';
import { adminService } from '@/services/adminService';
import { browserVaultUiCopy } from '@/lib/vaultUiCopy';

type Props = {
  value: string;
  onChange: (path: string) => void;
  layout?: 'inline' | 'stacked';
};

type VaultOption = {
  path: string;
  scope: string;
  vault_id?: string;
  active?: boolean;
};

export function DuckDbVaultSelector({ value, onChange, layout = 'stacked' }: Props) {
  const copy = useMemo(() => browserVaultUiCopy(), []);
  const [vaults, setVaults] = useState<VaultOption[]>([]);
  const [creating, setCreating] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [newName, setNewName] = useState('');
  const [newDescription, setNewDescription] = useState('');
  const [createError, setCreateError] = useState<string | null>(null);
  const [createMsg, setCreateMsg] = useState<string | null>(null);

  const reload = () =>
    adminService.listVaults().then((r) => setVaults(r.vaults || []));

  useEffect(() => {
    reload().catch(() => setVaults([]));
  }, []);

  useEffect(() => {
    if (!value && vaults.length > 0) {
      onChange(vaults.find((v) => v.active)?.path || vaults[0].path);
    }
  }, [vaults, value, onChange]);

  const createVault = async () => {
    const name = newName.trim();
    if (!name) {
      setCreateError(copy.nameRequired);
      return;
    }
    setCreating(true);
    setCreateError(null);
    setCreateMsg(null);
    try {
      const res = await adminService.createVault({
        name,
        description: newDescription.trim() || undefined,
      });
      await reload();
      const path = res.vault?.path;
      if (path) onChange(path);
      setCreateMsg(`${copy.createdPrefix} ${res.vault?.vault_id || name}`);
      setNewName('');
      setNewDescription('');
      setShowForm(false);
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : copy.createFailed);
    } finally {
      setCreating(false);
    }
  };

  const selectEl = (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={
        layout === 'inline'
          ? 'min-w-0 max-w-xl flex-1 rounded-lg border px-3 py-2 font-mono text-xs dark:border-dark-border dark:bg-dark-bg'
          : 'mt-1.5 w-full rounded-lg border border-gov-gray-200 bg-white px-3 py-2 font-mono text-xs dark:border-dark-border dark:bg-dark-bg'
      }
    >
      {vaults.length === 0 && <option value="">{copy.noVaults}</option>}
      {vaults.map((v) => (
        <option key={v.path} value={v.path}>
          [{v.scope}
          {v.active ? copy.activeSuffix : ''}] {v.path}
        </option>
      ))}
    </select>
  );

  const createBlock = (
    <div className="mt-2 space-y-2">
      {!showForm ? (
        <button
          type="button"
          onClick={() => {
            setShowForm(true);
            setCreateError(null);
            setCreateMsg(null);
          }}
          className="inline-flex items-center gap-1 rounded-lg border border-gov-gray-200 px-2 py-1 text-[11px] font-medium text-gov-gray-700 dark:border-dark-border dark:text-dark-text"
        >
          <Plus size={12} /> {copy.newVault}
        </button>
      ) : (
        <div className="space-y-1.5 rounded-lg border border-gov-gray-200 p-2 dark:border-dark-border">
          <label className="block text-[10px] font-bold text-gov-gray-500">
            {copy.name}
            <input
              type="text"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="my-data"
              className="mt-0.5 w-full rounded-lg border px-2 py-1 font-mono text-xs dark:border-dark-border dark:bg-dark-bg"
              disabled={creating}
            />
          </label>
          <label className="block text-[10px] font-bold text-gov-gray-500">
            {copy.descriptionOptional}
            <input
              type="text"
              value={newDescription}
              onChange={(e) => setNewDescription(e.target.value)}
              className="mt-0.5 w-full rounded-lg border px-2 py-1 text-xs dark:border-dark-border dark:bg-dark-bg"
              disabled={creating}
            />
          </label>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={createVault}
              disabled={creating}
              className="rounded-lg bg-gov-blue-700 px-2 py-1 text-[10px] text-white disabled:opacity-50"
            >
              {creating ? copy.creating : copy.create}
            </button>
            <button
              type="button"
              onClick={() => setShowForm(false)}
              disabled={creating}
              className="rounded-lg border px-2 py-1 text-[10px] dark:border-dark-border"
            >
              {copy.cancel}
            </button>
          </div>
        </div>
      )}
      {createMsg && <p className="text-[10px] text-green-700">{createMsg}</p>}
      {createError && <p className="text-[10px] text-red-600">{createError}</p>}
    </div>
  );

  if (layout === 'inline') {
    return (
      <div className="space-y-1">
        <label className="flex items-center gap-2 text-sm">
          <Database size={16} className="shrink-0 text-gov-blue-600 dark:text-dark-cyan" />
          <span className="shrink-0 text-gov-gray-500 dark:text-dark-muted">{copy.vault}</span>
          {selectEl}
        </label>
        {createBlock}
      </div>
    );
  }

  return (
    <div>
      <label className="block text-sm">
        <span className="inline-flex items-center gap-1.5 font-medium text-gov-gray-800 dark:text-dark-text">
          <Database size={14} className="text-gov-blue-600 dark:text-dark-cyan" />
          {copy.vault}
        </span>
        {selectEl}
      </label>
      {createBlock}
    </div>
  );
}
