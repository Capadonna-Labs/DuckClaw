'use client';

import { useAuthStore } from '@/store/authStore';
import { useRouter } from 'next/navigation';
import ThemeToggle from '@/components/settings/ThemeToggle';
import SettingsSection from '@/components/settings/SettingsSection';
import { User, Palette, LogOut, Users } from 'lucide-react';
import { PageShell } from '@/components/admin/PageShell';
import { ADMIN_USERS } from '@/config/adminUsers';

export default function SettingsPage() {
  const { usuario, logout } = useAuthStore();
  const router = useRouter();

  const handleLogout = () => {
    logout();
    router.replace('/login');
  };

  return (
    <PageShell className="max-w-4xl mx-auto pb-12">
      <h1 className="text-3xl font-black dark:text-dark-text">Ajustes</h1>
      <p className="text-sm text-gov-gray-500 dark:text-dark-muted mb-6">
        Perfil, usuarios de consola, tema y sesión
      </p>
      <SettingsSection titulo="Perfil" icono={<User size={22} />}>
        <p className="font-bold">{usuario?.nombre}</p>
        <p className="text-sm text-gov-gray-500">{usuario?.email}</p>
        <p className="text-xs uppercase mt-2">Rol: {usuario?.rol}</p>
      </SettingsSection>
      <SettingsSection
        titulo="Usuarios de consola"
        descripcion="Definidos en src/config/adminUsers.ts (solo desarrollo/demo)"
        icono={<Users size={22} />}
      >
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-gov-gray-500">
              <th className="pb-2">Email</th>
              <th className="pb-2">Nombre</th>
              <th className="pb-2">Rol</th>
            </tr>
          </thead>
          <tbody>
            {ADMIN_USERS.map((u) => (
              <tr key={u.email} className="border-t dark:border-dark-border">
                <td className="py-2 font-mono text-xs">{u.email}</td>
                <td className="py-2">{u.nombre}</td>
                <td className="py-2 capitalize">{u.rol}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </SettingsSection>
      <SettingsSection titulo="Apariencia" icono={<Palette size={22} />}>
        <ThemeToggle />
      </SettingsSection>
      <button
        type="button"
        onClick={handleLogout}
        className="flex items-center gap-2 px-4 py-2 text-red-600 border border-red-200 rounded-xl text-sm font-bold"
      >
        <LogOut size={18} /> Cerrar sesión
      </button>
    </PageShell>
  );
}
