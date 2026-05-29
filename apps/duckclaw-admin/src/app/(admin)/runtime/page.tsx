'use client';

import { useCallback, useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import { useAuthStore } from '@/store/authStore';
import {
  clampInput,
  LIMITS,
  validateRuntimeKey,
  validateRuntimeValue,
} from '@/lib/validation';
import { Trash2 } from 'lucide-react';

export default function RuntimePage() {
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
      setMsg('Encolado en db-writer (puede tardar unos segundos)');
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
    <div className="space-y-6">
      <header>
        <p className="text-xs font-black uppercase tracking-[0.18em] text-gov-blue-700 dark:text-dark-cyan">
          Admin avanzado
        </p>
        <h1 className="text-3xl font-black dark:text-dark-text mt-1">Runtime overrides</h1>
        <p className="text-sm text-gov-gray-500 dark:text-dark-muted mt-1">
          Sobrescribe configuración por bóveda y conversación. Úsalo solo para soporte,
          debugging o migraciones controladas.
        </p>
      </header>

      <section className="rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-200">
        <p className="font-bold">Cambios sensibles</p>
        <p className="mt-1">
          Las escrituras se encolan vía Redis y las aplica `db-writer`. Verifica `vault`,
          `chat_id` y key antes de guardar.
        </p>
      </section>

      <div className="flex flex-wrap gap-3">
        <select
          value={vault}
          onChange={(e) => setVault(e.target.value)}
          className="px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-surface text-sm font-mono"
        >
          {vaults.map((v) => (
            <option key={v.path} value={v.path}>
              {v.path}
            </option>
          ))}
        </select>
        <input
          value={chatId}
          onChange={(e) => setChatId(e.target.value)}
          className="px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-surface text-sm font-mono"
          placeholder="chat_id"
        />
        <button
          type="button"
          onClick={load}
          className="px-3 py-2 border rounded-xl text-sm dark:border-dark-border"
        >
          Recargar
        </button>
      </div>

      {error && <p className="text-red-600 text-sm">{error}</p>}
      {msg && <p className="text-green-700 text-sm">{msg}</p>}

      <table className="w-full text-sm bg-white dark:bg-dark-surface rounded-2xl border dark:border-dark-border overflow-hidden">
        <thead className="bg-gov-gray-50 dark:bg-dark-bg">
          <tr>
            <th className="px-4 py-2 text-left">scope</th>
            <th className="px-4 py-2 text-left">key</th>
            <th className="px-4 py-2 text-left">value</th>
            {canWrite && <th className="px-4 py-2 w-12" />}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={canWrite ? 4 : 3} className="px-4 py-6 text-center text-gov-gray-500">
                Sin filas para este chat_id
              </td>
            </tr>
          )}
          {rows.map((r) => (
            <tr key={`${r.scope ?? 'x'}-${r.key}`} className="border-t dark:border-dark-border">
              <td className="px-4 py-2 text-xs capitalize text-gov-gray-500">{r.scope ?? '—'}</td>
              <td className="px-4 py-2 font-mono text-xs">{r.key}</td>
              <td className="px-4 py-2 font-mono text-xs truncate max-w-xl" title={r.value}>
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

      {canWrite && (
        <RuntimeUpsertForm
          newKey={newKey}
          setNewKey={setNewKey}
          newVal={newVal}
          setNewVal={setNewVal}
          onSave={save}
        />
      )}
    </div>
  );
}

function RuntimeUpsertForm({
  newKey,
  setNewKey,
  newVal,
  setNewVal,
  onSave,
}: {
  newKey: string;
  setNewKey: (v: string) => void;
  newVal: string;
  setNewVal: (v: string) => void;
  onSave: () => void;
}) {
  return (
    <div className="flex flex-wrap gap-2 max-w-3xl">
      <input
        value={newKey}
        onChange={(e) => setNewKey(clampInput(e.target.value, LIMITS.runtimeKey))}
        maxLength={LIMITS.runtimeKey}
        placeholder="key (sufijo; se guarda como chat_{id}_key)"
        className="flex-1 px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-surface font-mono text-sm"
      />
      <input
        value={newVal}
        onChange={(e) => setNewVal(clampInput(e.target.value, LIMITS.runtimeValue))}
        maxLength={LIMITS.runtimeValue}
        placeholder="value"
        className="flex-[2] px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-surface font-mono text-sm"
      />
      <button
        type="button"
        onClick={onSave}
        className="px-4 py-2 bg-gov-blue-700 text-white rounded-xl text-sm font-bold"
      >
        Upsert
      </button>
    </div>
  );
}
