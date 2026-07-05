'use client';

import Link from 'next/link';
import { ChevronDown, LogOut, Sun, Moon, Menu, MessageSquare, RefreshCw, User } from 'lucide-react';
import { useLayoutUiStore } from '@/store/layoutUiStore';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/store/authStore';
import { obtenerIniciales } from '@/lib/utils';
import { useTheme } from '@/components/shared/ThemeProvider';
import { useEffect, useRef, useState } from 'react';
import { adminService } from '@/services/adminService';
import { formatOpsOutput } from '@/lib/formatOpsOutput';
import { PlatformStatusStrip } from '@/components/admin/GatewayStatusBadge';
import { useGatewayHealthStore } from '@/store/gatewayHealthStore';

interface TopbarProps {
  onMenuClick?: () => void;
}

async function waitForGatewayHealth(maxAttempts = 20): Promise<boolean> {
  for (let i = 0; i < maxAttempts; i += 1) {
    const delayMs = Math.min(1500 * (i + 1), 6000);
    await new Promise((resolve) => window.setTimeout(resolve, delayMs));
    const health = await useGatewayHealthStore.getState().refresh(true);
    if (health?.status === 'ok') return true;
  }
  return false;
}

export default function Topbar({ onMenuClick }: TopbarProps) {
  const { usuario, logout } = useAuthStore();
  const { theme, toggleTheme } = useTheme();
  const { sidebarOpen, toggleSidebar, chatDrawerOpen, toggleChatDrawer } = useLayoutUiStore();
  const router = useRouter();
  const canRunOps = usuario?.rol === 'admin';
  const [stackRestarting, setStackRestarting] = useState(false);
  const [stackRestartMessage, setStackRestartMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!stackRestartMessage?.startsWith('Stack recuperado')) return;
    const timer = window.setTimeout(() => {
      window.location.reload();
    }, 4000);
    return () => window.clearTimeout(timer);
  }, [stackRestartMessage]);

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

  const restartStack = async () => {
    if (!canRunOps) return;
    setStackRestarting(true);
    setStackRestartMessage(null);
    useGatewayHealthStore.getState().beginRecovery();
    try {
      const result = await adminService.runOps('restart_stack');
      if (!result.ok) {
        setStackRestartMessage(
          formatOpsOutput({
            ok: false,
            exit_code: result.exit_code,
            stdout: result.stdout,
            stderr: result.stderr,
            executed_via: result.executed_via,
            op_id: 'restart_stack',
          })
        );
        return;
      }
      setStackRestartMessage('Recuperando gateway (health check)…');
      const healthy = await waitForGatewayHealth();
      setStackRestartMessage(
        healthy
          ? 'Stack recuperado: migraciones + PM2. Recargando consola…'
          : 'Migraciones y PM2 OK, pero /health no respondió aún. Espera 30s y recarga manualmente.'
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'No se pudo reiniciar el stack';
      setStackRestartMessage(msg);
    } finally {
      useGatewayHealthStore.getState().endRecovery();
      await useGatewayHealthStore.getState().refresh(true);
      setStackRestarting(false);
    }
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
        <div className="flex items-center gap-2">
          <PlatformStatusStrip />
          {canRunOps && (
            <div className="relative">
              <button
                type="button"
                onClick={() => void restartStack()}
                disabled={stackRestarting}
                className="inline-flex items-center gap-2 rounded-xl border border-gov-blue-100 px-3 py-2 text-xs font-black text-gov-blue-800 hover:bg-gov-blue-50 disabled:opacity-50 dark:border-dark-border dark:text-dark-cyan dark:hover:bg-dark-bg"
                title="Migraciones DuckDB + reinicio DuckClaw-DB-Writer y DuckClaw-Gateway (PM2)"
              >
                <RefreshCw size={14} className={stackRestarting ? 'animate-spin' : ''} />
                <span className="hidden sm:inline">
                  {stackRestarting ? 'Reiniciando...' : 'Reiniciar stack'}
                </span>
              </button>
              {stackRestartMessage && (
                <div className="absolute right-0 top-full z-50 mt-2 w-80 max-w-[calc(100vw-2rem)] rounded-2xl border bg-white p-3 text-xs font-semibold text-gov-gray-700 shadow-lg dark:border-dark-border dark:bg-dark-surface dark:text-dark-text whitespace-pre-wrap">
                  {stackRestartMessage}
                </div>
              )}
            </div>
          )}
        </div>
        <button
          type="button"
          onClick={toggleChatDrawer}
          className={`p-2 rounded-lg transition-colors ${
            chatDrawerOpen
              ? 'bg-gov-blue-700 text-white hover:bg-gov-blue-800'
              : 'text-gov-gray-500 hover:bg-gov-gray-100 dark:hover:bg-dark-bg'
          }`}
          aria-label={chatDrawerOpen ? 'Cerrar asistente' : 'Abrir asistente'}
          aria-expanded={chatDrawerOpen}
          title="Asistente"
        >
          <MessageSquare size={20} />
        </button>
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
          isAdmin={canRunOps}
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
  isAdmin,
}: {
  displayName: string;
  email: string;
  initials: string;
  onLogout: () => void;
  isAdmin?: boolean;
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
        <div className="absolute right-0 top-full mt-2 w-56 rounded-2xl border bg-white dark:bg-dark-surface dark:border-dark-border shadow-lg p-2 z-50">
          <div className={`px-3 py-2 border-b dark:border-dark-border mb-1 ${isAdmin ? 'lg:hidden' : ''}`}>
            <p className="text-xs font-bold dark:text-dark-text truncate">{displayName}</p>
            {email && (
              <p className="text-[10px] text-gov-gray-500 font-mono truncate">{email}</p>
            )}
          </div>
          {isAdmin && (
            <Link
              href="/administracion?tab=cuenta"
              onClick={() => setUserMenuOpen(false)}
              className="w-full flex items-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold text-gov-blue-800 hover:bg-gov-blue-50 dark:text-dark-cyan dark:hover:bg-dark-bg"
            >
              <User size={16} />
              Mi cuenta
            </Link>
          )}
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
