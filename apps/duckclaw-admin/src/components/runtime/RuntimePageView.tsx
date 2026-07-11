'use client';

import { useCallback, useEffect, useState } from 'react';
import { RefreshCw, Trash2 } from 'lucide-react';
import { adminService } from '@/services/adminService';
import { useAuthStore } from '@/store/authStore';
import {
  clampInput,
  LIMITS,
  validateRuntimeKey,
  validateRuntimeValue,
} from '@/lib/validation';
import { ViewChrome, type EmbeddedViewProps } from '@/components/admin/embeddedView';

export default function RuntimePageView({ embedded = false }: EmbeddedViewProps) {
  const { usuario } = useAuthStore();
  const canWrite = usuario?.rol === 'admin';

  const [vaults, setVaults] = useState<{ path: string }[]>([]);
  const [vault, setVault] = useState('');
  const [chatId, setChatId] = useState('default');
  const [rows, setRows] = useState<{ key: string; value: string; scope?: string }[]>([]);
  const [newKey, setNewKey] = useState('');
  const [newVal, setNewVal] = useState('');
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!vault) return;
    setError(null);
    adminService
      .getRuntimeConfig(vault, chatId)
      .then((r) => {
        setRows(r.rows ?? []);
        if (r.warning) setMsg(r.warning);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, [vault, chatId]);

  useEffect(() => {
    adminService.listVaults().then((r) => {
      setVaults(r.vaults);
      if (r.vaults[0]) setVault(r.vaults[0].path);
    });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const save = async () => {
    if (!canWrite) return;
    const keyErr = validateRuntimeKey(newKey);
    const valErr = validateRuntimeValue(newVal);
    if (keyErr || valErr) {
      setError(keyErr ?? valErr);
      return;
    }
    setError(null);
    setMsg(null);
    try {
      await adminService.putRuntimeConfig({
        vault_path: vault,
        chat_id: chatId,
        key: newKey.trim(),
        value: newVal,
      });
      setMsg('Escritura encolada en db-writer');
      setNewKey('');
      setNewVal('');
      setTimeout(load, 800);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    }
  };

  const removeKey = async (key: string) => {
    if (!canWrite || !confirm(`¿Eliminar key "${key}"?`)) return;
    try {
      await adminService.deleteRuntimeConfig(vault, chatId, key);
      setMsg('Eliminación encolada');
      setTimeout(load, 800);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    }
  };

  return (
    <ViewChrome embedded={embedded}>
      <div className="space-y-4">
        {!embedded && (
          <header className="border-b border-gov-gray-200 pb-4 dark:border-dark-border">
            <h1 className="text-2xl font-bold text-gov-gray-900 dark:text-dark-text">Runtime</h1>
            <p className="mt-1 text-sm text-gov-gray-600 dark:text-dark-muted">
              Overrides en agent_config por bóveda y chat_id
            </p>
          </header>
        )}

        {error && (
          <p className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-600 dark:bg-red-950/40 dark:text-red-400">
            {error}
          </p>
        )}
        {msg && (
          <p className="rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200">
            {msg}
          </p>
        )}

        <div className="grid gap-4 lg:grid-cols-12">
          <section className="rounded-xl border border-gov-gray-200 bg-white dark:border-dark-border dark:bg-dark-surface lg:col-span-8">
            <div className="border-b border-gov-gray-100 px-4 py-3 dark:border-dark-border">
              <h2 className="text-base font-semibold text-gov-gray-900 dark:text-dark-text">
                agent_config
              </h2>
              <p className="mt-0.5 text-xs text-gov-gray-500 dark:text-dark-muted">
                {rows.length} fila{rows.length === 1 ? '' : 's'} · chat_id{' '}
                <span className="font-mono">{chatId}</span>
              </p>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gov-gray-50 text-left dark:bg-dark-bg">
                  <tr>
                    <th className="px-4 py-2 text-xs font-semibold">scope</th>
                    <th className="px-4 py-2 text-xs font-semibold">key</th>
                    <th className="px-4 py-2 text-xs font-semibold">value</th>
                    {canWrite && <th className="w-12 px-4 py-2" />}
                  </tr>
                </thead>
                <tbody>
                  {rows.length === 0 && (
                    <tr>
                      <td
                        colSpan={canWrite ? 4 : 3}
                        className="px-4 py-10 text-center text-sm text-gov-gray-500 dark:text-dark-muted"
                      >
                        Sin filas para este chat_id
                      </td>
                    </tr>
                  )}
                  {rows.map((r) => (
                    <tr
                      key={`${r.scope ?? 'x'}-${r.key}`}
                      className="border-t dark:border-dark-border"
                    >
                      <td className="px-4 py-2 text-xs capitalize text-gov-gray-500">
                        {r.scope ?? '—'}
                      </td>
                      <td className="px-4 py-2 font-mono text-xs">{r.key}</td>
                      <td
                        className="max-w-md truncate px-4 py-2 font-mono text-xs"
                        title={r.value}
                      >
                        {r.value}
                      </td>
                      {canWrite && (
                        <td className="px-4 py-2">
                          <button
                            type="button"
                            onClick={() => removeKey(r.key)}
                            className="text-red-600"
                            aria-label="Eliminar"
                          >
                            <Trash2 size={16} />
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <aside className="space-y-4 lg:col-span-4">
            <section className="rounded-xl border border-gov-gray-200 bg-gov-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
              <p className="text-sm font-semibold text-gov-gray-900 dark:text-dark-text">¿Qué es Runtime?</p>
              <p className="mt-2 text-xs leading-relaxed text-gov-gray-600 dark:text-dark-muted">
                Claves en la tabla <code className="font-mono">agent_config</code> de tu bóveda DuckDB.
                Los agentes las leen en caliente (metas legacy, toggles de sesión, estado de /loop).
                Las escrituras pasan por db-writer — no edites DuckDB a mano salvo que sepas el contrato.
              </p>
            </section>

            <section className="rounded-xl border border-gov-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
              <p className="text-sm font-semibold text-gov-gray-900 dark:text-dark-text">Contexto</p>
              <div className="mt-3 space-y-3">
                <label className="block text-xs">
                  <span className="font-medium text-gov-gray-600 dark:text-dark-muted">Bóveda</span>
                  <select
                    value={vault}
                    onChange={(e) => setVault(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-gov-gray-200 bg-white px-3 py-2 font-mono text-xs dark:border-dark-border dark:bg-dark-bg"
                  >
                    {vaults.map((v) => (
                      <option key={v.path} value={v.path}>
                        {v.path}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="block text-xs">
                  <span className="font-medium text-gov-gray-600 dark:text-dark-muted">chat_id</span>
                  <input
                    value={chatId}
                    onChange={(e) => setChatId(e.target.value)}
                    className="mt-1 w-full rounded-lg border border-gov-gray-200 bg-white px-3 py-2 font-mono text-xs dark:border-dark-border dark:bg-dark-bg"
                    placeholder="default"
                  />
                </label>
                <button
                  type="button"
                  onClick={load}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-gov-gray-200 px-3 py-2 text-xs font-semibold dark:border-dark-border"
                >
                  <RefreshCw size={14} />
                  Recargar
                </button>
              </div>
            </section>

            {canWrite && (
              <section className="rounded-xl border border-gov-gray-200 bg-white p-4 dark:border-dark-border dark:bg-dark-surface">
                <p className="text-sm font-semibold text-gov-gray-900 dark:text-dark-text">
                  Nueva clave
                </p>
                <div className="mt-3 space-y-2">
                  <input
                    value={newKey}
                    onChange={(e) => setNewKey(clampInput(e.target.value, LIMITS.runtimeKey))}
                    maxLength={LIMITS.runtimeKey}
                    placeholder="key"
                    className="w-full rounded-lg border border-gov-gray-200 px-3 py-2 font-mono text-xs dark:border-dark-border dark:bg-dark-bg"
                  />
                  <input
                    value={newVal}
                    onChange={(e) => setNewVal(clampInput(e.target.value, LIMITS.runtimeValue))}
                    maxLength={LIMITS.runtimeValue}
                    placeholder="value"
                    className="w-full rounded-lg border border-gov-gray-200 px-3 py-2 font-mono text-xs dark:border-dark-border dark:bg-dark-bg"
                  />
                  <button
                    type="button"
                    onClick={save}
                    className="w-full rounded-lg bg-gov-blue-700 px-4 py-2 text-xs font-semibold text-white"
                  >
                    Guardar
                  </button>
                </div>
              </section>
            )}
          </aside>
        </div>
      </div>
    </ViewChrome>
  );
}
