'use client';

import { useCallback, useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import type { SharedDbGrant } from '@/types/admin';
import { Database, Trash2 } from 'lucide-react';

type Props = {
  tenantId: string;
};

export function SharedGrantsPanel({ tenantId }: Props) {
  const [grants, setGrants] = useState<SharedDbGrant[]>([]);
  const [dbPath, setDbPath] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [userId, setUserId] = useState('');
  const [resourceKey, setResourceKey] = useState('default');

  const load = useCallback(() => {
    adminService
      .listSharedGrants(tenantId)
      .then((r) => {
        setGrants(r.grants ?? []);
        setDbPath(r.db_path ?? '');
        setError(r.warning ?? null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, [tenantId]);

  useEffect(() => {
    load();
  }, [load]);

  const grant = async () => {
    if (!userId.trim() || !resourceKey.trim()) return;
    setError(null);
    setMsg(null);
    try {
      await adminService.grantSharedAccess({
        tenant_id: tenantId,
        user_id: userId.trim(),
        resource_key: resourceKey.trim().toLowerCase(),
      });
      setMsg('Grant guardado');
      setUserId('');
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    }
  };

  const revoke = async (uid: string, rk: string) => {
    if (!confirm(`¿Revocar ${rk} para ${uid}?`)) return;
    try {
      await adminService.revokeSharedAccess(tenantId, uid, rk);
      setMsg('Grant revocado');
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-gov-gray-500">
        <Database size={14} className="inline mr-1" />
        <span className="font-mono">{dbPath || 'user_shared_db_access'}</span>
      </p>
      {error && <p className="text-red-600 text-sm">{error}</p>}
      {msg && <p className="text-green-700 text-sm">{msg}</p>}

      <div className="overflow-hidden rounded-2xl border dark:border-dark-border">
        <table className="w-full text-sm">
          <thead className="bg-gov-gray-50 dark:bg-dark-bg text-left">
            <tr>
              <th className="px-4 py-2">user_id</th>
              <th className="px-4 py-2">resource_key</th>
              <th className="px-4 py-2 w-16" />
            </tr>
          </thead>
          <tbody>
            {grants.length === 0 && (
              <tr>
                <td colSpan={3} className="px-4 py-6 text-gov-gray-500 text-center">
                  Sin grants: compatibilidad abierta a rutas shared válidas.
                </td>
              </tr>
            )}
            {grants.map((g) => (
              <tr
                key={`${g.user_id}-${g.resource_key}`}
                className="border-t dark:border-dark-border"
              >
                <td className="px-4 py-2 font-mono text-xs">{g.user_id}</td>
                <td className="px-4 py-2 font-mono text-xs">{g.resource_key}</td>
                <td className="px-4 py-2">
                  <button
                    type="button"
                    onClick={() => revoke(g.user_id, g.resource_key)}
                    className="text-red-600"
                    aria-label="Revocar"
                  >
                    <Trash2 size={16} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="p-4 rounded-2xl bg-gov-gray-50 dark:bg-dark-bg space-y-3">
        <p className="text-xs font-bold uppercase text-gov-gray-500">Nuevo grant</p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          <input
            value={userId}
            onChange={(e) => setUserId(e.target.value)}
            placeholder="user_id Telegram"
            className="px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-surface font-mono text-sm"
          />
          <input
            value={resourceKey}
            onChange={(e) => setResourceKey(e.target.value)}
            placeholder="default | * | clave custom"
            className="px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-surface font-mono text-sm"
            list="resource-keys"
          />
          <datalist id="resource-keys">
            <option value="default" />
            <option value="*" />
          </datalist>
          <button
            type="button"
            onClick={grant}
            className="px-4 py-2 bg-gov-blue-700 text-white rounded-xl text-sm font-bold"
          >
            Otorgar
          </button>
        </div>
      </div>
    </div>
  );
}
