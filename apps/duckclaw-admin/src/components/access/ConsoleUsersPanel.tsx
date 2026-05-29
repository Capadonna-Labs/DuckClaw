'use client';

import { useCallback, useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import type { AdminRole, ConsoleUser } from '@/types/admin';
import { KeyRound, UserPlus, Trash2 } from 'lucide-react';

export function ConsoleUsersPanel() {
  const [users, setUsers] = useState<ConsoleUser[]>([]);
  const [dbPath, setDbPath] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const [email, setEmail] = useState('');
  const [nombre, setNombre] = useState('');
  const [rol, setRol] = useState<AdminRole>('user');
  const [password, setPassword] = useState('');
  const [initials, setInitials] = useState('');

  const load = useCallback(() => {
    adminService
      .listConsoleUsers()
      .then((r) => {
        setUsers(r.users ?? []);
        setDbPath(r.db_path ?? '');
        setError(r.warning ?? null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const addUser = async () => {
    if (!email.trim() || !password.trim()) return;
    setError(null);
    setMsg(null);
    try {
      await adminService.upsertConsoleUser({
        email: email.trim(),
        nombre: nombre.trim() || email.trim(),
        rol,
        password,
        initials: initials.trim() || email.slice(0, 2).toUpperCase(),
      });
      setMsg('Usuario guardado');
      setEmail('');
      setNombre('');
      setPassword('');
      setInitials('');
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    }
  };

  const resetPassword = async (userEmail: string) => {
    const pw = prompt(`Nueva contraseña para ${userEmail}`);
    if (!pw?.trim()) return;
    try {
      await adminService.patchConsoleUser(userEmail, { password: pw });
      setMsg(`Contraseña actualizada para ${userEmail}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    }
  };

  const deactivate = async (userEmail: string) => {
    if (!confirm(`¿Desactivar ${userEmail}?`)) return;
    try {
      await adminService.deleteConsoleUser(userEmail);
      setMsg('Usuario desactivado');
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-gov-gray-500 font-mono">{dbPath || 'hub gateway'}</p>
      {error && <p className="text-red-600 text-sm">{error}</p>}
      {msg && <p className="text-green-700 text-sm">{msg}</p>}

      <div className="overflow-hidden rounded-2xl border dark:border-dark-border">
        <table className="w-full text-sm">
          <thead className="bg-gov-gray-50 dark:bg-dark-bg text-left">
            <tr>
              <th className="px-4 py-2">email</th>
              <th className="px-4 py-2">nombre</th>
              <th className="px-4 py-2">rol</th>
              <th className="px-4 py-2">activo</th>
              <th className="px-4 py-2 w-24" />
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.email} className="border-t dark:border-dark-border">
                <td className="px-4 py-2 font-mono text-xs">{u.email}</td>
                <td className="px-4 py-2">{u.nombre}</td>
                <td className="px-4 py-2 capitalize">{u.rol}</td>
                <td className="px-4 py-2">{u.active ? 'sí' : 'no'}</td>
                <td className="px-4 py-2 flex gap-2">
                  <button
                    type="button"
                    onClick={() => resetPassword(u.email)}
                    className="text-gov-blue-700"
                    aria-label="Reset password"
                  >
                    <KeyRound size={16} />
                  </button>
                  {u.active && (
                    <button
                      type="button"
                      onClick={() => deactivate(u.email)}
                      className="text-red-600"
                      aria-label="Desactivar"
                    >
                      <Trash2 size={16} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="p-4 rounded-2xl bg-gov-gray-50 dark:bg-dark-bg space-y-3">
        <p className="text-xs font-bold uppercase text-gov-gray-500 flex items-center gap-2">
          <UserPlus size={16} /> Nuevo usuario consola
        </p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          <input
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="email"
            className="px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-surface text-sm"
          />
          <input
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            placeholder="nombre"
            className="px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-surface text-sm"
          />
          <select
            value={rol}
            onChange={(e) => setRol(e.target.value as AdminRole)}
            className="px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-surface text-sm"
          >
            <option value="user">user</option>
            <option value="admin">admin</option>
          </select>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="contraseña"
            className="px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-surface text-sm"
          />
          <input
            value={initials}
            onChange={(e) => setInitials(e.target.value)}
            placeholder="iniciales"
            className="px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-surface text-sm"
          />
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
