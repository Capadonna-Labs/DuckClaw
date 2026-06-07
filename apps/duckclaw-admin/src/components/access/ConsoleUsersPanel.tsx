'use client';

import { useCallback, useEffect, useState } from 'react';
import { adminService } from '@/services/adminService';
import type { AdminRole, ConsoleUser } from '@/types/admin';
import { KeyRound, UserPlus, Trash2 } from 'lucide-react';
import ConfirmDangerModal from '@/components/admin/ConfirmDangerModal';

export function ConsoleUsersPanel() {
  const [users, setUsers] = useState<ConsoleUser[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);
  const [pendingDeactivate, setPendingDeactivate] = useState<ConsoleUser | null>(null);
  const [resetPasswordUser, setResetPasswordUser] = useState<ConsoleUser | null>(null);
  const [resetPasswordValue, setResetPasswordValue] = useState('');
  const [resetPasswordBusy, setResetPasswordBusy] = useState(false);
  const [showInactive, setShowInactive] = useState(false);

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

  const visibleUsers = showInactive ? users : users.filter((user) => user.active);
  const inactiveCount = users.filter((user) => !user.active).length;

  const resetPassword = async () => {
    if (!resetPasswordUser) return;
    const pw = resetPasswordValue.trim();
    if (!pw) {
      setError('Escribe una nueva contraseña.');
      return;
    }
    setResetPasswordBusy(true);
    setError(null);
    try {
      await adminService.patchConsoleUser(resetPasswordUser.email, { password: pw });
      setMsg(`Contraseña actualizada para ${resetPasswordUser.email}`);
      setResetPasswordUser(null);
      setResetPasswordValue('');
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    } finally {
      setResetPasswordBusy(false);
    }
  };

  const deactivate = async () => {
    if (!pendingDeactivate) return;
    try {
      await adminService.deleteConsoleUser(pendingDeactivate.email);
      setMsg('Usuario desactivado');
      setPendingDeactivate(null);
      load();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error');
    }
  };

  return (
    <div className="space-y-4">
      {error && <p className="text-red-600 text-sm">{error}</p>}
      {msg && <p className="text-green-700 text-sm">{msg}</p>}

      <div className="flex flex-wrap items-center justify-between gap-2 rounded-2xl border bg-gov-gray-50 px-3 py-2 text-xs dark:border-dark-border dark:bg-dark-bg">
        <p className="text-gov-gray-600 dark:text-dark-muted">
          {showInactive
            ? 'Mostrando usuarios activos e inactivos.'
            : `${inactiveCount} usuarios inactivos ocultos.`}
        </p>
        <button
          type="button"
          onClick={() => setShowInactive((value) => !value)}
          className="font-bold text-gov-blue-700 dark:text-dark-cyan"
        >
          {showInactive ? 'Ocultar inactivos' : 'Ver inactivos'}
        </button>
      </div>

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
            {visibleUsers.map((u) => (
              <tr key={u.email} className="border-t dark:border-dark-border">
                <td className="px-4 py-2 font-mono text-xs">{u.email}</td>
                <td className="px-4 py-2">{u.nombre}</td>
                <td className="px-4 py-2 capitalize">{u.rol}</td>
                <td className="px-4 py-2">{u.active ? 'sí' : 'no'}</td>
                <td className="px-4 py-2 flex gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      setResetPasswordUser(u);
                      setResetPasswordValue('');
                      setError(null);
                      setMsg(null);
                    }}
                    className="text-gov-blue-700"
                    aria-label={`Cambiar contraseña de ${u.email}`}
                  >
                    <KeyRound size={16} />
                  </button>
                  {u.active && (
                    <button
                      type="button"
                    onClick={() => setPendingDeactivate(u)}
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
      <ConfirmDangerModal
        isOpen={Boolean(pendingDeactivate)}
        title="Desactivar usuario"
        description="El usuario no podrá volver a ingresar a la consola hasta que se reactive."
        confirmLabel="Desactivar"
        details={
          pendingDeactivate
            ? [
                { label: 'Email', value: pendingDeactivate.email },
                { label: 'Rol', value: pendingDeactivate.rol },
              ]
            : []
        }
        onCancel={() => setPendingDeactivate(null)}
        onConfirm={() => void deactivate()}
      />
      {resetPasswordUser && (
        <>
          <div className="fixed inset-0 bg-slate-900/70 backdrop-blur-sm z-[200]" aria-hidden />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="reset-password-title"
            className="fixed top-1/2 left-1/2 z-[201] w-full max-w-md -translate-x-1/2 -translate-y-1/2 overflow-hidden rounded-2xl border bg-white shadow-2xl dark:border-dark-border dark:bg-dark-surface"
          >
            <div className="border-b p-5 dark:border-dark-border">
              <h2 id="reset-password-title" className="text-lg font-bold dark:text-dark-text">
                Nueva contraseña
              </h2>
              <p className="mt-1 text-sm text-gov-gray-500 dark:text-dark-muted">
                Cambiarás la contraseña de{' '}
                <span className="font-mono text-xs">{resetPasswordUser.email}</span>.
              </p>
            </div>
            <div className="space-y-3 p-5">
              <input
                type="password"
                value={resetPasswordValue}
                onChange={(event) => setResetPasswordValue(event.target.value)}
                placeholder="Nueva contraseña"
                className="w-full rounded-xl border px-3 py-2 text-sm dark:border-dark-border dark:bg-dark-bg"
                autoFocus
              />
              <p className="text-xs text-gov-gray-500">
                El valor anterior no se muestra. La actualización queda registrada en auditoría.
              </p>
            </div>
            <div className="flex justify-end gap-3 border-t bg-gov-gray-50 p-4 dark:border-dark-border dark:bg-dark-bg">
              <button
                type="button"
                disabled={resetPasswordBusy}
                onClick={() => {
                  setResetPasswordUser(null);
                  setResetPasswordValue('');
                }}
                className="rounded-xl border px-4 py-2 text-sm font-semibold dark:border-dark-border"
              >
                Cancelar
              </button>
              <button
                type="button"
                disabled={resetPasswordBusy || !resetPasswordValue.trim()}
                onClick={() => void resetPassword()}
                className="rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-bold text-white disabled:opacity-50"
              >
                {resetPasswordBusy ? 'Guardando…' : 'Actualizar contraseña'}
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
