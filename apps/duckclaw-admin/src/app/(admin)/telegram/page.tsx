'use client';

import { useCallback, useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import SettingsSection from '@/components/settings/SettingsSection';
import { PageShell } from '@/components/admin/PageShell';
import { useAuthStore } from '@/store/authStore';
import type { WhitelistUser } from '@/types/admin';
import { MessageSquare, Users, Trash2, UserPlus } from 'lucide-react';

export default function TelegramPage() {
  const { usuario } = useAuthStore();
  const canWrite = usuario?.rol === 'admin';

  const [routes, setRoutes] = useState<{ bot: string; path: string }[]>([]);
  const [env, setEnv] = useState<Record<string, string>>({});
  const [tokenKey, setTokenKey] = useState('TELEGRAM_BOT_TOKEN');
  const [tokenVal, setTokenVal] = useState('');
  const [envMsg, setEnvMsg] = useState<string | null>(null);

  const [tenantId, setTenantId] = useState('default');
  const [users, setUsers] = useState<WhitelistUser[]>([]);
  const [dbPath, setDbPath] = useState('');
  const [wlWarning, setWlWarning] = useState<string | null>(null);
  const [wlError, setWlError] = useState<string | null>(null);
  const [wlMsg, setWlMsg] = useState<string | null>(null);

  const [newUserId, setNewUserId] = useState('');
  const [newUsername, setNewUsername] = useState('');
  const [newRole, setNewRole] = useState<'admin' | 'user'>('user');

  const loadWhitelist = useCallback(() => {
    adminService
      .getTelegramWhitelist(tenantId)
      .then((r) => {
        setUsers(r.users ?? []);
        setDbPath(r.db_path ?? '');
        setWlWarning(r.warning ?? null);
      })
      .catch((e) => setWlError(e instanceof Error ? e.message : 'Error'));
  }, [tenantId]);

  useEffect(() => {
    adminService.getTelegramRoutes().then((r) => setRoutes(r.routes));
    adminService.getEnv().then((e) => setEnv(e.values));
  }, []);

  useEffect(() => {
    loadWhitelist();
  }, [loadWhitelist]);

  const saveToken = async () => {
    await adminService.patchEnv({ [tokenKey]: tokenVal });
    setEnvMsg('Token actualizado (enmascarado en lectura)');
    setTokenVal('');
    adminService.getEnv().then((e) => setEnv(e.values));
  };

  const addUser = async () => {
    if (!canWrite || !newUserId.trim()) return;
    setWlError(null);
    setWlMsg(null);
    try {
      await adminService.upsertWhitelistUser({
        tenant_id: tenantId,
        user_id: newUserId.trim(),
        username: newUsername.trim() || 'Usuario',
        role: newRole,
      });
      setWlMsg('Usuario guardado en authorized_users');
      setNewUserId('');
      setNewUsername('');
      loadWhitelist();
    } catch (e) {
      setWlError(e instanceof Error ? e.message : 'Error');
    }
  };

  const removeUser = async (userId: string) => {
    if (!canWrite || !confirm(`¿Quitar user_id ${userId} del tenant ${tenantId}?`)) return;
    setWlError(null);
    try {
      await adminService.deleteWhitelistUser(tenantId, userId);
      setWlMsg('Usuario eliminado');
      loadWhitelist();
    } catch (e) {
      setWlError(e instanceof Error ? e.message : 'Error');
    }
  };

  return (
    <PageShell>
      <header>
        <h1 className="text-3xl font-black dark:text-dark-text">Telegram</h1>
        <p className="text-sm text-gov-gray-500 dark:text-dark-muted mt-1">
          Webhooks, tokens y whitelist (misma tabla que <code className="font-mono text-xs">/team</code>)
        </p>
      </header>

      <SettingsSection
        titulo="Rutas webhook"
        descripcion="DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES"
        icono={<MessageSquare size={22} />}
      >
        <ul className="space-y-2 text-sm font-mono">
          {routes.length === 0 && <li className="text-gov-gray-500">Sin rutas configuradas</li>}
          {routes.map((r) => (
            <li key={r.bot} className="p-2 bg-gov-gray-50 dark:bg-dark-bg rounded-lg">
              {r.bot} → {r.path}
            </li>
          ))}
        </ul>
      </SettingsSection>

      <SettingsSection
        titulo="Token bot"
        descripcion="Progressive disclosure — valor nuevo"
        icono={<MessageSquare size={22} />}
      >
        <div className="space-y-3 max-w-lg">
          <select
            value={tokenKey}
            onChange={(e) => setTokenKey(e.target.value)}
            className="w-full px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-bg text-sm"
          >
            {Object.keys(env)
              .filter((k) => k.startsWith('TELEGRAM'))
              .map((k) => (
                <option key={k} value={k}>
                  {k} ({env[k]})
                </option>
              ))}
            <option value="TELEGRAM_BOT_TOKEN">TELEGRAM_BOT_TOKEN (nuevo)</option>
          </select>
          <input
            type="password"
            value={tokenVal}
            onChange={(e) => setTokenVal(e.target.value)}
            placeholder="Nuevo token (no se muestra el actual)"
            className="w-full px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-bg"
            disabled={!canWrite}
          />
          {canWrite && (
            <button
              type="button"
              onClick={saveToken}
              className="px-4 py-2 bg-gov-blue-700 text-white rounded-xl text-sm font-bold"
            >
              Guardar token
            </button>
          )}
          {envMsg && <p className="text-green-700 text-sm">{envMsg}</p>}
        </div>
      </SettingsSection>

      <SettingsSection
        titulo="Whitelist Telegram Guard"
        descripcion={`main.authorized_users · ${dbPath || 'hub gateway'}`}
        icono={<Users size={22} />}
      >
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            <input
              value={tenantId}
              onChange={(e) => setTenantId(e.target.value)}
              className="px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-bg text-sm font-mono"
              placeholder="tenant_id"
            />
            <button
              type="button"
              onClick={loadWhitelist}
              className="px-3 py-2 border rounded-xl text-sm dark:border-dark-border"
            >
              Recargar
            </button>
          </div>

          {wlWarning && <p className="text-amber-700 text-sm">{wlWarning}</p>}
          {wlError && <p className="text-red-600 text-sm">{wlError}</p>}
          {wlMsg && <p className="text-green-700 text-sm">{wlMsg}</p>}

          <div className="overflow-hidden rounded-2xl border dark:border-dark-border">
            <table className="w-full text-sm">
              <thead className="bg-gov-gray-50 dark:bg-dark-bg text-left">
                <tr>
                  <th className="px-4 py-2">user_id</th>
                  <th className="px-4 py-2">username</th>
                  <th className="px-4 py-2">role</th>
                  {canWrite && <th className="px-4 py-2 w-20" />}
                </tr>
              </thead>
              <tbody>
                {users.length === 0 && (
                  <tr>
                    <td colSpan={canWrite ? 4 : 3} className="px-4 py-6 text-gov-gray-500 text-center">
                      Sin usuarios para este tenant. Usa /team en Telegram o añade abajo.
                    </td>
                  </tr>
                )}
                {users.map((u) => (
                  <tr key={u.user_id} className="border-t dark:border-dark-border">
                    <td className="px-4 py-2 font-mono text-xs">{u.user_id}</td>
                    <td className="px-4 py-2">{u.username || '—'}</td>
                    <td className="px-4 py-2 capitalize">{u.role}</td>
                    {canWrite && (
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
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {canWrite && (
            <div className="p-4 rounded-2xl bg-gov-gray-50 dark:bg-dark-bg space-y-3">
              <p className="text-xs font-bold uppercase text-gov-gray-500 flex items-center gap-2">
                <UserPlus size={16} /> Añadir usuario
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
          )}
        </div>
      </SettingsSection>
    </PageShell>
  );
}
