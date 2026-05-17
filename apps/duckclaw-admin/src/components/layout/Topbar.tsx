'use client';

import { LogOut, Sun, Moon, Menu, PanelLeftOpen } from 'lucide-react';
import { useLayoutUiStore } from '@/store/layoutUiStore';
import { PanelToggleButton } from '@/components/layout/PanelToggleButton';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store/authStore';
import { obtenerIniciales } from '@/lib/utils';
import { useTheme } from '@/components/shared/ThemeProvider';

interface TopbarProps {
  title: string;
  onMenuClick?: () => void;
}

export default function Topbar({ title, onMenuClick }: TopbarProps) {
  const { usuario, logout } = useAuthStore();
  const { theme, toggleTheme } = useTheme();
  const { sidebarOpen, setSidebarOpen } = useLayoutUiStore();
  const router = useRouter();

  const handleLogout = () => {
    logout();
    router.replace('/login');
  };

  return (
    <header
      role="banner"
      className="h-16 bg-white border-b border-gov-gray-100 shadow-sm px-4 md:px-6 flex items-center justify-between shrink-0 dark:bg-dark-surface dark:border-dark-border"
    >
      <TopbarLeft
        title={title}
        email={usuario?.email}
        onMenuClick={onMenuClick}
        sidebarOpen={sidebarOpen}
        onShowSidebar={() => setSidebarOpen(true)}
      />
      <div className="flex items-center gap-2 md:gap-4">
        <button
          type="button"
          onClick={toggleTheme}
          className="p-2 rounded-lg text-gov-gray-500 hover:bg-gov-gray-100 dark:hover:bg-dark-bg"
          aria-label="Cambiar tema"
        >
          {theme === 'light' ? <Moon size={20} /> : <Sun size={20} />}
        </button>
        <div className="hidden sm:flex items-center gap-3 pl-3 border-l dark:border-dark-border">
          <div className="text-right hidden lg:block">
            <p className="text-sm font-bold dark:text-dark-text">{usuario?.nombre}</p>
            <p className="text-[10px] text-gov-gray-500 capitalize">{usuario?.rol}</p>
          </div>
          <div className="w-9 h-9 rounded-full bg-gov-blue-700 text-white flex items-center justify-center text-xs font-bold">
            {usuario?.initials ?? obtenerIniciales(usuario?.nombre || '')}
          </div>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          className="flex items-center gap-2 px-3 py-2 text-sm font-semibold rounded-lg hover:bg-red-50 hover:text-red-700 dark:hover:bg-red-950/30"
        >
          <LogOut size={18} />
          <span className="hidden md:inline">Salir</span>
        </button>
      </div>
    </header>
  );
}

function TopbarLeft({
  title,
  email,
  onMenuClick,
  sidebarOpen,
  onShowSidebar,
}: {
  title: string;
  email?: string;
  onMenuClick?: () => void;
  sidebarOpen: boolean;
  onShowSidebar: () => void;
}) {
  return (
    <div className="flex items-center gap-3 flex-wrap">
      <button
        type="button"
        onClick={onMenuClick}
        className="lg:hidden p-2 rounded-lg"
        aria-label="Menú"
      >
        <Menu size={20} />
      </button>
      {!sidebarOpen && (
        <PanelToggleButton
          open={false}
          onToggle={onShowSidebar}
          openLabel="Ocultar menú"
          closedLabel="Menú"
          openIcon={PanelLeftOpen}
          closedIcon={PanelLeftOpen}
          title="Mostrar menú lateral"
          className="hidden lg:inline-flex"
        />
      )}
      <div>
        <h2 className="text-lg font-semibold dark:text-dark-text">{title}</h2>
        {email && <p className="text-[10px] text-gov-gray-500 hidden sm:block">{email}</p>}
      </div>
    </div>
  );
}
