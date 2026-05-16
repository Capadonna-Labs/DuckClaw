'use client';

import { LogOut, Sun, Moon, Menu } from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import { obtenerIniciales } from '@/lib/utils';
import { useTheme } from '@/components/shared/ThemeProvider';
import NotificationBell from './NotificationBell';

interface TopbarProps {
  title: string;
  onMenuClick?: () => void;
}

export default function Topbar({ title, onMenuClick }: TopbarProps) {
  const { usuario, logout } = useAuthStore();
  const { theme, toggleTheme } = useTheme();

  return (
    <header 
      role="banner"
      className="h-16 bg-white border-b border-gov-gray-100 shadow-sm px-4 md:px-6 flex items-center justify-between shrink-0 transition-colors duration-300 dark:bg-dark-surface dark:border-dark-border"
    >
      {/* Left Side: Menu Toggle (Mobile) & Section Info */}
      <div className="flex items-center gap-4">
        <button
          onClick={onMenuClick}
          className="lg:hidden p-2 -ml-2 rounded-lg text-gov-gray-500 hover:bg-gov-gray-100 dark:text-dark-muted dark:hover:bg-dark-bg transition-colors"
          aria-label="Abrir menú"
        >
          <Menu size={20} />
        </button>
        
        <div className="flex flex-col">
          <h2 className="text-lg md:text-xl font-semibold text-gov-gray-900 leading-tight dark:text-dark-text truncate max-w-[150px] md:max-w-none">
            {title}
          </h2>
          <p className="hidden sm:block text-[10px] md:text-xs text-gov-gray-500 dark:text-dark-muted">
            Distrito de Medellín · {usuario?.secretariaNombre ?? 'Cargando...'}
          </p>
        </div>
      </div>

      {/* Right Side: User Profile & Actions */}
      <div className="flex items-center gap-2 md:gap-6">
        {/* Toggle Modo Oscuro */}
        <button
          onClick={toggleTheme}
          className="p-2 rounded-lg text-gov-gray-500 hover:bg-gov-gray-100 dark:text-dark-muted dark:hover:bg-dark-bg transition-colors"
          title={`Cambiar a modo ${theme === 'light' ? 'oscuro' : 'claro'}`}
        >
          {theme === 'light' ? <Moon size={20} /> : <Sun size={20} />}
        </button>

        {/* Centro de Notificaciones */}
        <NotificationBell />

        <div className="flex items-center gap-3 md:pl-6 md:border-l md:border-gov-gray-100 md:dark:border-dark-border">
          <div className="hidden lg:flex flex-col items-end">
            <span className="text-sm font-bold text-gov-gray-900 leading-none dark:text-dark-text">
              {usuario?.nombreCompleto}
            </span>
            <span className="text-[10px] font-bold text-gov-blue-600 uppercase tracking-tighter mt-1 dark:text-dark-cyan">
              {usuario?.secretariaNombre}
            </span>
          </div>
          
          <div className="bg-gov-blue-700 text-white rounded-full w-8 h-8 md:w-10 md:h-10 flex items-center justify-center text-xs md:text-sm font-bold shadow-lg shadow-gov-blue-900/20 border-2 border-white dark:border-dark-surface dark:bg-dark-accent">
            {obtenerIniciales(usuario?.nombreCompleto || '')}
          </div>
        </div>

        <button
          onClick={() => logout()}
          className="text-gov-gray-500 hover:text-sem-red transition-colors p-2 rounded-lg hover:bg-sem-red-bg group relative dark:text-dark-muted dark:hover:bg-sem-red/10"
          title="Cerrar sesión"
          aria-label="Cerrar sesión"
        >
          <LogOut className="w-[18px] h-[18px] md:w-5 md:h-5" />
        </button>
      </div>
    </header>
  );
}
