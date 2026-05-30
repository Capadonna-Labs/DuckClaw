'use client';

import { useCallback, useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import type { WhitelistUser } from '@/types/admin';
import { Trash2, UserPlus } from 'lucide-react';

type Props = {
  tenantId: string;
  onTenantIdChange: (v: string) => void;
};

export function TelegramUsersPanel({ tenantId, onTenantIdChange }: Props) {
  const [users, setUsers] = useState<WhitelistUser[]>([]);
  const [effectiveTenant, setEffectiveTenant] = useState<string | null>(null);
  const [wlHint, setWlHint] = useState<string | null>(null);
  const [wlWarning, setWlWarning] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const [newUserId, setNewUserId] = useState('');
  const [newUsername, setNewUsername] = useState('');
  const [newRole, setNewRole] = useState<'admin' | 'user'>('user');

  const load = useCallback(() => {
    adminService
      .getTelegramWhitelist(tenantId)
      .then((r) => {
        setUsers(r.users ?? []);
        setWlWarning(r.warning ?? null);
        setWlHint(r.hint ?? null);
        const eff = r.effective_tenant_id ?? r.tenant_id;
        if (eff) {
          setEffectiveTenant(eff);
          if (tenantId === 'default' && eff !== 'default') {
            onTenantIdChange(eff);
          }
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, [tenantId, onTenantIdChange]);

  useEffect(() => {
    load();
  }, [load]);

  const addUser = async () => {
    if (!newUserId.trim()) return;
    setError(null);
    setMsg(null);
    try {
      await adminService.upsertWhitelistUser({
        tenant_id: tenantId,
        user_id: newUserId.trim(),
        username: newUsername.trim() || 'Usuario',
        role: newRole,
      });
      setMsg(`Usuario guardado (tenant «${effectiveTenant ?? tenantId}»)`);
      setNewUserId('');
      setNewUsername('');
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    }
  };

  const removeUser = async (userId: string) => {
    if (!confirm(`¿Quitar user_id ${userId} del tenant ${tenantId}?`)) return;
    setError(null);
    try {
      await adminService.deleteWhitelistUser(tenantId, userId);
      setMsg('Usuario eliminado');
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-2">
        <input
          value={tenantId}
          onChange={(e) => onTenantIdChange(e.target.value)}
          className="px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-bg text-sm font-mono"
          placeholder="tenant_id"
        />
        <button
          type="button"
          onClick={load}
          className="px-3 py-2 border rounded-xl text-sm dark:border-dark-border"
        >
          Recargar
        </button>
      </div>

      {wlWarning && <p className="text-amber-700 text-sm">{wlWarning}</p>}
      {wlHint && <p className="text-amber-800 dark:text-amber-200 text-sm">{wlHint}</p>}
      {effectiveTenant && (
        <p className="text-xs text-gov-gray-500">
          Tenant activo: <strong className="font-mono">{effectiveTenant}</strong>
        </p>
      )}
      {error && <p className="text-red-600 text-sm">{error}</p>}
      {msg && <p className="text-green-700 text-sm">{msg}</p>}

      <div className="overflow-hidden rounded-2xl border dark:border-dark-border">
        <table className="w-full text-sm">
          <thead className="bg-gov-gray-50 dark:bg-dark-bg text-left">
            <tr>
              <th className="px-4 py-2">user_id</th>
              <th className="px-4 py-2">username</th>
              <th className="px-4 py-2">role</th>
              <th className="px-4 py-2 w-20" />
            </tr>
          </thead>
          <tbody>
            {users.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-gov-gray-500 text-center">
                  Sin usuarios para este tenant.
                </td>
              </tr>
            )}
            {users.map((u) => (
              <tr key={u.user_id} className="border-t dark:border-dark-border">
                <td className="px-4 py-2 font-mono text-xs">{u.user_id}</td>
                <td className="px-4 py-2">{u.username || '—'}</td>
                <td className="px-4 py-2 capitalize">{u.role}</td>
                <td className="px-4 py-2">
                  <button
                    type="button"
                    onClick={() => removeUser(u.user_id)}
                    className="text-red-600 hover:text-red-800"
                    aria-label="Eliminar"
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
        <p className="text-xs font-bold uppercase text-gov-gray-500 flex items-center gap-2">
          <UserPlus size={16} /> Añadir usuario Telegram
        </p>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-2">
          <input
            value={newUserId}
            onChange={(e) => setNewUserId(e.target.value)}
            placeholder="user_id (Telegram)"
            className="px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-surface font-mono text-sm"
          />
          <input
            value={newUsername}
            onChange={(e) => setNewUsername(e.target.value)}
            placeholder="username"
            className="px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-surface text-sm"
          />
          <select
            value={newRole}
            onChange={(e) => setNewRole(e.target.value as 'admin' | 'user')}
            className="px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-surface text-sm"
          >
            <option value="user">user</option>
            <option value="admin">admin</option>
          </select>
          <button
            type="button"
            onClick={addUser}
            className="px-4 py-2 bg-gov-blue-700 text-white rounded-xl text-sm font-bold"
          >
            Guardar
          </button>
        </div>
      </div>
    </div>
  );
}
