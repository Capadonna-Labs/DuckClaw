'use client';

import { useAuthStore } from '@/store/authStore';
import ThemeToggle from '@/components/settings/ThemeToggle';
import SettingsSection from '@/components/settings/SettingsSection';
import { LogOut, Palette, User } from 'lucide-react';

type AccountSettingsPanelProps = {
  onLogout: () => void | Promise<void>;
};

export function AccountSettingsPanel({ onLogout }: AccountSettingsPanelProps) {
  const { usuario } = useAuthStore();

  return (
    <div className="space-y-6 max-w-2xl">
      <SettingsSection titulo="Perfil" icono={<User size={22} />}>
        <p className="font-bold dark:text-dark-text">{usuario?.nombre}</p>
        <p className="text-sm text-gov-gray-500 dark:text-dark-muted">{usuario?.email}</p>
        <p className="text-xs uppercase mt-2 text-gov-gray-500 dark:text-dark-muted">
          Rol: {usuario?.rol}
        </p>
      </SettingsSection>

      <SettingsSection titulo="Apariencia" icono={<Palette size={22} />}>
        <ThemeToggle />
      </SettingsSection>

      <button
        type="button"
        onClick={() => void onLogout()}
        className="flex items-center gap-2 px-4 py-2 rounded-xl border dark:border-dark-border text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30"
      >
        <LogOut size={18} />
        Cerrar sesión
      </button>
    </div>
  );
}
