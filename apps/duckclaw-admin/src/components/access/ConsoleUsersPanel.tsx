'use client';

import { useCallback, useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import type { AdminRole, ConsoleUser } from '@/types/admin';
import { Pencil, UserPlus } from 'lucide-react';

type EditDraft = {
  nombre: string;
  initials: string;
  rol: AdminRole;
  password: string;
};

function editDraftFromUser(user: ConsoleUser): EditDraft {
  return {
    nombre: user.nombre,
    initials: user.initials,
    rol: user.rol === 'viewer' ? 'user' : user.rol,
    password: '',
  };
}

function UserEditModal({
  user,
  busy,
  onClose,
  onSave,
}: {
  user: ConsoleUser;
  busy: boolean;
  onClose: () => void;
  onSave: (draft: EditDraft) => Promise<void>;
}) {
  const [draft, setDraft] = useState<EditDraft>(() => editDraftFromUser(user));

  useEffect(() => {
    setDraft(editDraftFromUser(user));
  }, [user]);

  return (
    <>
      <div className="fixed inset-0 bg-slate-900/70 backdrop-blur-sm z-[200]" aria-hidden />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="edit-user-title"
        className="fixed top-1/2 left-1/2 z-[201] w-full max-w-md -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-2xl border bg-white shadow-2xl dark:border-dark-border dark:bg-dark-surface"
      >
        <div className="border-b p-5 dark:border-dark-border">
          <h2 id="edit-user-title" className="text-lg font-bold dark:text-dark-text">
            Editar usuario
          </h2>
          <p className="mt-1 font-mono text-xs text-gov-gray-500 dark:text-dark-muted">{user.email}</p>
        </div>
        <div className="space-y-3 p-5">
          <label className="block text-xs font-bold uppercase text-gov-gray-500">
            Nombre
            <input
              value={draft.nombre}
              onChange={(e) => setDraft((prev) => ({ ...prev, nombre: e.target.value }))}
              className="mt-1 w-full rounded-xl border px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
            />
          </label>
          <label className="block text-xs font-bold uppercase text-gov-gray-500">
            Iniciales
            <input
              value={draft.initials}
              onChange={(e) => setDraft((prev) => ({ ...prev, initials: e.target.value }))}
              maxLength={8}
              className="mt-1 w-full rounded-xl border px-3 py-2 text-sm font-mono dark:border-dark-border dark:bg-dark-bg"
            />
          </label>
          <label className="block text-xs font-bold uppercase text-gov-gray-500">
            Rol
            <select
              value={draft.rol}
              onChange={(e) => setDraft((prev) => ({ ...prev, rol: e.target.value as AdminRole }))}
              className="mt-1 w-full rounded-xl border px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
            >
              <option value="user">user</option>
              <option value="admin">admin</option>
            </select>
          </label>
          <label className="block text-xs font-bold uppercase text-gov-gray-500">
            Nueva contraseña (opcional)
            <input
              type="password"
              value={draft.password}
              onChange={(e) => setDraft((prev) => ({ ...prev, password: e.target.value }))}
              placeholder="Dejar vacío para no cambiar"
              className="mt-1 w-full rounded-xl border px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
            />
          </label>
          <p className="text-xs text-gov-gray-500 dark:text-dark-muted leading-relaxed">
            El login valida contra el hash en DuckDB (<code className="font-mono">admin_console_users</code>).
            El <code className="font-mono">.env</code> solo siembra la contraseña inicial si la tabla estaba vacía;
            cambiar aquí no modifica el <code className="font-mono">.env</code>, y al revés tampoco actualiza el hash
            ya guardado.
          </p>
        </div>
        <div className="flex justify-end gap-3 border-t bg-gov-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
          <button
            type="button"
            disabled={busy}
            onClick={onClose}
            className="rounded-xl border px-4 py-2 text-sm font-semibold dark:border-dark-border"
          >
            Cancelar
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void onSave(draft)}
            className="rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
          >
            {busy ? 'Guardando…' : 'Guardar cambios'}
          </button>
        </div>
      </div>
    </>
  );
}

export function ConsoleUsersPanel() {
  const [users, setUsers] = useState<ConsoleUser[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [editUser, setEditUser] = useState<ConsoleUser | null>(null);
  const [editBusy, setEditBusy] = useState(false);

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
        setError(r.warning ?? null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const activeUsers = users.filter((user) => user.active);

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
      setMsg('Usuario creado');
      setEmail('');
      setNombre('');
      setPassword('');
      setInitials('');
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    }
  };

  const saveEdit = async (draft: EditDraft) => {
    if (!editUser) return;
    setEditBusy(true);
    setError(null);
    try {
      const body: {
        nombre: string;
        initials: string;
        rol: AdminRole;
        password?: string;
      } = {
        nombre: draft.nombre.trim() || editUser.email,
        initials:
          draft.initials.trim().toUpperCase().slice(0, 8) ||
          editUser.email.slice(0, 2).toUpperCase(),
        rol: draft.rol,
      };
      const pw = draft.password.trim();
      if (pw) body.password = pw;
      await adminService.patchConsoleUser(editUser.email, body);
      setMsg(`Usuario actualizado: ${editUser.email}`);
      setEditUser(null);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo guardar');
    } finally {
      setEditBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      {error && <p className="text-red-600 text-sm">{error}</p>}
      {msg && <p className="text-green-700 text-sm">{msg}</p>}

      <div className="overflow-x-auto rounded-2xl border dark:border-dark-border">
        <table className="w-full min-w-[560px] text-sm">
          <thead className="bg-gov-gray-50 dark:bg-dark-bg text-left">
            <tr>
              <th className="px-4 py-2 font-bold">Email</th>
              <th className="px-4 py-2 font-bold">Nombre</th>
              <th className="px-4 py-2 font-bold">Iniciales</th>
              <th className="px-4 py-2 font-bold">Rol</th>
              <th className="px-4 py-2 w-24" />
            </tr>
          </thead>
          <tbody>
            {activeUsers.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-8 text-center text-gov-gray-500">
                  Sin usuarios activos.
                </td>
              </tr>
            ) : (
              activeUsers.map((user) => (
                <tr key={user.email} className="border-t dark:border-dark-border">
                  <td className="px-4 py-3 font-mono text-xs">{user.email}</td>
                  <td className="px-4 py-3">{user.nombre}</td>
                  <td className="px-4 py-3 font-mono text-xs">{user.initials}</td>
                  <td className="px-4 py-3 capitalize">{user.rol}</td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      onClick={() => {
                        setEditUser(user);
                        setError(null);
                        setMsg(null);
                      }}
                      className="inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs font-bold text-gov-blue-700 dark:border-dark-border dark:text-dark-cyan"
                    >
                      <Pencil size={14} />
                      Editar
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      <div className="rounded-2xl bg-gov-gray-50 p-4 dark:bg-dark-bg space-y-3">
        <p className="text-xs font-bold uppercase text-gov-gray-500 flex items-center gap-2">
          <UserPlus size={16} /> Nuevo usuario
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
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
          <input
            value={initials}
            onChange={(e) => setInitials(e.target.value)}
            placeholder="iniciales"
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
            placeholder="contraseña inicial"
            className="px-3 py-2 border rounded-xl dark:border-dark-border dark:bg-dark-surface text-sm"
          />
          <button
            type="button"
            onClick={() => void addUser()}
            className="px-4 py-2 bg-gov-blue-700 text-white rounded-xl text-sm font-bold"
          >
            Crear usuario
          </button>
        </div>
      </div>

      {editUser && (
        <UserEditModal
          user={editUser}
          busy={editBusy}
          onClose={() => setEditUser(null)}
          onSave={saveEdit}
        />
      )}
    </div>
  );
}
