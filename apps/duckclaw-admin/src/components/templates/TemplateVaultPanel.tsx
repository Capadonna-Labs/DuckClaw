'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { Database, Save } from 'lucide-react';
import { adminService } from '@/services/adminService';
import type { VaultBinding, VaultOption } from '@/types/admin';

function optionKey(o: VaultOption): string {
  return o.scope === 'private' ? `private:${o.vault_id}` : `shared:${o.path}`;
}

function bindingToKey(binding: VaultBinding | null | undefined): string {
  if (!binding?.scope) return '';
  if (binding.scope === 'private') return `private:${binding.vault_id || ''}`;
  return `shared:${binding.path || ''}`;
}

type TemplateVaultPanelProps = {
  workerId: string;
  canWrite: boolean;
};

export function TemplateVaultPanel({ workerId, canWrite }: TemplateVaultPanelProps) {
  const [vaultUserId, setVaultUserId] = useState('');
  const [options, setOptions] = useState<VaultOption[]>([]);
  const [selected, setSelected] = useState('');
  const [resolvedPath, setResolvedPath] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    adminService.getPlaygroundConfig().then((c) => {
      setVaultUserId(c.telegram_user_id || '');
    });
  }, []);

  const reload = useCallback(() => {
    if (!workerId) return;
    setLoading(true);
    setErr(null);
    const uid = vaultUserId.trim() || undefined;
    Promise.all([
      adminService.getTemplateVaultOptions(workerId, uid),
      adminService.getTemplateVaultBinding(workerId, uid),
    ])
      .then(([optsRes, bindRes]) => {
        setOptions(optsRes.options || []);
        setVaultUserId(optsRes.vault_user_id || vaultUserId);
        setSelected(bindingToKey(bindRes.binding));
        setResolvedPath(bindRes.resolved_path);
      })
      .catch((e) => setErr(e instanceof Error ? e.message : 'Error'))
      .finally(() => setLoading(false));
  }, [workerId, vaultUserId]);

  useEffect(() => {
    reload();
  }, [reload]);

  const grouped = useMemo(() => {
    const priv = options.filter((o) => o.scope === 'private');
    const shared = options.filter((o) => o.scope === 'shared');
    return { priv, shared };
  }, [options]);

  const save = async () => {
    if (!canWrite) return;
    setMsg(null);
    setErr(null);
    try {
      if (!selected) {
        await adminService.putTemplateVaultBinding(workerId, { scope: '' });
        setMsg('Bóveda desvinculada (hub / registry por defecto)');
      } else {
        const [scope, rest] = selected.split(':', 2);
        if (scope === 'private') {
          await adminService.putTemplateVaultBinding(workerId, {
            scope: 'private',
            vault_id: rest,
          });
        } else {
          await adminService.putTemplateVaultBinding(workerId, {
            scope: 'shared',
            path: rest,
          });
        }
        setMsg('Bóveda guardada en manifest.yaml');
      }
      reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : 'Error al guardar');
    }
  };

  return (
    <div className="mb-4 p-3 rounded-xl border dark:border-dark-border bg-white dark:bg-dark-surface space-y-2">
      <div className="flex items-center gap-2 text-xs font-bold text-gov-gray-700 dark:text-dark-text">
        <Database size={14} /> Bóveda DuckDB (/vault)
      </div>
      <p className="text-[10px] text-gov-gray-500 leading-snug">
        Archivos en <span className="font-mono">db/private/&lt;tu id&gt;/</span> y{' '}
        <span className="font-mono">db/shared/</span>. Afecta /vault y el sandbox de esta plantilla.
      </p>
      <label className="block text-[10px] font-bold text-gov-gray-500">
        ID bóveda (usuario)
        <input
          type="text"
          value={vaultUserId}
          onChange={(e) => setVaultUserId(e.target.value)}
          className="mt-0.5 w-full font-mono text-xs px-2 py-1 rounded-lg border dark:border-dark-border dark:bg-dark-bg"
          placeholder="1726618406"
        />
      </label>
      <label className="block text-[10px] font-bold text-gov-gray-500">
        Archivo .duckdb
        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          disabled={loading || !canWrite}
          className="mt-0.5 w-full font-mono text-xs px-2 py-1.5 rounded-lg border dark:border-dark-border dark:bg-dark-bg"
        >
          <option value="">— Sin binding (hub / registry) —</option>
          {grouped.priv.length > 0 && (
            <optgroup label="Privadas (tu usuario)">
              {grouped.priv.map((o) => (
                <option key={optionKey(o)} value={optionKey(o)}>
                  {o.label} ({o.vault_id})
                </option>
              ))}
            </optgroup>
          )}
          {grouped.shared.length > 0 && (
            <optgroup label="Compartidas">
              {grouped.shared.map((o) => (
                <option key={optionKey(o)} value={optionKey(o)}>
                  {o.label} — {o.path}
                </option>
              ))}
            </optgroup>
          )}
        </select>
      </label>
      {resolvedPath && (
        <p className="text-[10px] font-mono text-gov-gray-500 break-all">
          Ruta resuelta: {resolvedPath}
        </p>
      )}
      {msg && <p className="text-[10px] text-green-700">{msg}</p>}
      {err && <p className="text-[10px] text-red-600">{err}</p>}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={reload}
          disabled={loading}
          className="px-2 py-1 text-[10px] border rounded-lg dark:border-dark-border"
        >
          Actualizar lista
        </button>
        {canWrite && (
          <button
            type="button"
            onClick={save}
            className="px-2 py-1 text-[10px] bg-gov-blue-700 text-white rounded-lg flex items-center gap-1"
          >
            <Save size={12} /> Guardar bóveda
          </button>
        )}
      </div>
    </div>
  );
}
