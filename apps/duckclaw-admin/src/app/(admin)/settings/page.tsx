'use client';

import { useAuthStore } from '@/store/authStore';
import { useRouter } from 'next/navigation';
import ThemeToggle from '@/components/settings/ThemeToggle';
import SettingsSection from '@/components/settings/SettingsSection';
import { User, Palette, LogOut } from 'lucide-react';

export default function SettingsPage() {
  const { usuario, logout } = useAuthStore();
  const router = useRouter();

  return (
    <motionPage>
      <h1 className="text-3xl font-black dark:text-dark-text">Ajustes</h1>
      <p className="text-sm text-gov-gray-500 dark:text-dark-muted mb-6">
        Settings pattern — perfil, tema, sesión
      </p>
      <SettingsSection titulo="Perfil" icono={<User size={22} />}>
        <p className="font-bold">{usuario?.nombre}</p>
        <p className="text-sm text-gov-gray-500">{usuario?.email}</p>
        <p className="text-xs uppercase mt-2">Rol: {usuario?.rol}</p>
      </SettingsSection>
      <SettingsSection titulo="Apariencia" icono={<Palette size={22} />}>
        <ThemeToggle />
      </SettingsSection>
      <button
        type="button"
        onClick={() => {
          logout();
          router.push('/login');
        }}
        className="flex items-center gap-2 px-4 py-2 text-red-600 border border-red-200 rounded-xl text-sm font-bold"
      >
        <LogOut size={18} /> Cerrar sesión
      </button>
    </motionPage>
  );
}

function motionPage({ children }: { children: React.ReactNode }) {
  return <div className="max-w-4xl mx-auto space-y-8 pb-12">{children}</div>;
}
