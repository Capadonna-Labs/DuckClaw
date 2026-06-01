'use client';

import { ChevronDown, LogOut, Sun, Moon, Menu } from 'lucide-react';
import { useLayoutUiStore } from '@/store/layoutUiStore';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store/authStore';
import { obtenerIniciales } from '@/lib/utils';
import { useTheme } from '@/components/shared/ThemeProvider';
import { useEffect, useRef, useState } from 'react';

interface TopbarProps {
  onMenuClick?: () => void;
}

export default function Topbar({ onMenuClick }: TopbarProps) {
  const { usuario, logout } = useAuthStore();
  const { theme, toggleTheme } = useTheme();
  const { sidebarOpen, toggleSidebar } = useLayoutUiStore();
  const router = useRouter();

  const handleLogout = () => {
    logout();
    router.replace('/login');
  };

  const handleMenuToggle = () => {
    if (typeof window !== 'undefined' && window.matchMedia('(min-width: 1024px)').matches) {
      toggleSidebar();
      return;
    }
    onMenuClick?.();
  };

  return (
    <header
      role="banner"
      className="h-16 bg-white border-b border-gov-gray-100 shadow-sm px-4 md:px-6 flex items-center justify-between shrink-0 dark:bg-dark-surface dark:border-dark-border"
    >
      <TopbarLeft
        onMenuClick={handleMenuToggle}
        sidebarOpen={sidebarOpen}
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
        <UserMenu
          displayName={usuario?.nombre || usuario?.email || 'Usuario'}
          email={usuario?.email || ''}
          initials={usuario?.initials ?? obtenerIniciales(usuario?.nombre || usuario?.email || '')}
          onLogout={handleLogout}
        />
      </div>
    </header>
  );
}

function UserMenu({
  displayName,
  email,
  initials,
  onLogout,
}: {
  displayName: string;
  email: string;
  initials: string;
  onLogout: () => void;
}) {
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!userMenuOpen) return;
    const closeOnOutside = (event: MouseEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setUserMenuOpen(false);
    };
    document.addEventListener('mousedown', closeOnOutside);
    return () => document.removeEventListener('mousedown', closeOnOutside);
  }, [userMenuOpen]);

  return (
    <div ref={menuRef} className="relative pl-2 border-l dark:border-dark-border">
      <button
        type="button"
        onClick={() => setUserMenuOpen((open) => !open)}
        className="flex items-center gap-2 rounded-xl px-2 py-1.5 hover:bg-gov-gray-100 dark:hover:bg-dark-bg"
        aria-label="Menú de usuario"
        aria-expanded={userMenuOpen}
      >
        <span className="hidden lg:block text-right">
          <span className="block text-xs font-bold dark:text-dark-text max-w-40 truncate">
            {displayName}
          </span>
          {email && (
            <span className="block text-[10px] text-gov-gray-500 font-mono normal-case max-w-40 truncate">
              {email}
            </span>
          )}
        </span>
        <span className="w-9 h-9 rounded-full bg-gov-blue-700 text-white flex items-center justify-center text-xs font-bold">
          {initials}
        </span>
        <ChevronDown size={14} className={userMenuOpen ? 'rotate-180 transition-transform' : 'transition-transform'} />
      </button>
      {userMenuOpen && (
        <div className="absolute right-0 top-full mt-2 w-48 rounded-2xl border bg-white dark:bg-dark-surface dark:border-dark-border shadow-lg p-2 z-50">
          <button
            type="button"
            onClick={onLogout}
            className="w-full flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold text-red-700 hover:bg-red-50 dark:hover:bg-red-950/30"
          >
            <LogOut size={16} />
            Cerrar sesión
          </button>
        </div>
      )}
    </div>
  );
}

function TopbarLeft({
  onMenuClick,
  sidebarOpen,
}: {
  onMenuClick?: () => void;
  sidebarOpen: boolean;
}) {
  const menuLabel = sidebarOpen ? 'Ocultar menú lateral' : 'Mostrar menú lateral';

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={onMenuClick}
        className="p-2 rounded-lg text-gov-gray-600 hover:bg-gov-gray-100 dark:text-dark-muted dark:hover:bg-dark-bg"
        aria-label={menuLabel}
        title={menuLabel}
      >
        <Menu size={20} />
      </button>
    </div>
  );
}
