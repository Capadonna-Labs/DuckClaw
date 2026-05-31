'use client';

import { useAuthStore } from '@/store/authStore';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import ThemeToggle from '@/components/settings/ThemeToggle';
import SettingsSection from '@/components/settings/SettingsSection';
import { User, Palette, LogOut } from 'lucide-react';
import { PageShell } from '@/components/admin/PageShell';

export default function SettingsPage() {
  const { usuario, logout } = useAuthStore();
  const router = useRouter();

  const handleLogout = async () => {
    await logout();
    router.replace('/login');
  };

  return (
    <PageShell className="max-w-4xl mx-auto pb-12">
      <h1 className="text-3xl font-black dark:text-dark-text">Ajustes</h1>
      <p className="text-sm text-gov-gray-500 dark:text-dark-muted mb-6">
        Perfil, tema y sesión
      </p>
      <SettingsSection titulo="Perfil" icono={<User size={22} />}>
        <p className="font-bold">{usuario?.nombre}</p>
        <p className="text-sm text-gov-gray-500">{usuario?.email}</p>
        <p className="text-xs uppercase mt-2">Rol: {usuario?.rol}</p>
        {usuario?.rol === 'admin' && (
          <Link href="/admin/access" className="text-sm text-gov-blue-700 mt-2 inline-block">
            Gestionar usuarios y roles →
          </Link>
        )}
      </SettingsSection>
      <SettingsSection titulo="Apariencia" icono={<Palette size={22} />}>
        <ThemeToggle />
      </SettingsSection>
      <button
        type="button"
        onClick={handleLogout}
        className="mt-6 flex items-center gap-2 px-4 py-2 rounded-xl border dark:border-dark-border text-red-600"
      >
        <LogOut size={18} />
        Cerrar sesión
      </button>
    </PageShell>
  );
}
