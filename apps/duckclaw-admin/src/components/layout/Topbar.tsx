'use client';

import { Menu, Moon, RefreshCw, Sparkles, Sun } from 'lucide-react';
import { useLayoutUiStore } from '@/store/layoutUiStore';
import { usePathname } from 'next/navigation';
import { useAuthStore } from '@/store/authStore';
import { obtenerIniciales } from '@/lib/utils';
import { useTheme } from '@/components/shared/ThemeProvider';
import { useEffect, useState } from 'react';
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
  const { usuario } = useAuthStore();
  const { theme, toggleTheme } = useTheme();
  const { sidebarOpen, toggleSidebar, chatDrawerOpen, toggleChatDrawer } = useLayoutUiStore();
  const pathname = usePathname();
  const isChatTab = pathname === '/playground' || pathname.startsWith('/playground/');
  const canRunOps = usuario?.rol === 'admin';
  const [stackRestarting, setStackRestarting] = useState(false);
  const [stackRestartMessage, setStackRestartMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!stackRestartMessage?.startsWith('Stack recuperado')) return;
    const timer = window.setTimeout(() => {
      window.location.reload();
    }, 3000);
    return () => window.clearTimeout(timer);
  }, [stackRestartMessage]);

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
                className="inline-flex min-h-[36px] items-center gap-1.5 rounded-xl border border-gov-blue-100 px-2.5 py-2 text-xs font-bold text-gov-blue-800 hover:bg-gov-blue-50 disabled:opacity-50 dark:border-dark-border dark:text-dark-cyan dark:hover:bg-dark-bg"
                title="Reinicia gateway, db-writer y heartbeat (migraciones DuckDB + PM2)"
                aria-label={stackRestarting ? 'Reiniciando sistema' : 'Reiniciar sistema'}
              >
                <RefreshCw size={17} className={stackRestarting ? 'animate-spin' : ''} />
                <span className="hidden sm:inline whitespace-nowrap">
                  {stackRestarting ? 'Reiniciando…' : 'Reiniciar sistema'}
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
        />
        {!isChatTab && (
          <button
            type="button"
            onClick={toggleChatDrawer}
            className={`p-2 rounded-lg transition-colors ${
              chatDrawerOpen
                ? 'bg-gov-blue-700 text-white hover:bg-gov-blue-800'
                : 'text-gov-blue-700 hover:bg-gov-blue-50 dark:text-dark-cyan dark:hover:bg-dark-bg'
            }`}
            aria-label={chatDrawerOpen ? 'Cerrar asistente IA' : 'Abrir asistente IA'}
            aria-expanded={chatDrawerOpen}
            title="Asistente IA"
          >
            <Sparkles size={20} />
          </button>
        )}
      </div>
    </header>
  );
}

function UserMenu({
  displayName,
  email,
  initials,
}: {
  displayName: string;
  email: string;
  initials: string;
}) {
  return (
    <div className="pl-2 border-l dark:border-dark-border">
      <div
        className="flex items-center gap-2 rounded-xl px-2 py-1.5"
        aria-label={`Sesión: ${displayName}`}
      >
        <span className="w-9 h-9 shrink-0 rounded-full bg-gov-blue-700 text-white flex items-center justify-center text-xs font-bold">
          {initials}
        </span>
        <span className="hidden lg:block min-w-0 text-left">
          <span className="block text-xs font-bold dark:text-dark-text truncate max-w-[12rem]">
            {displayName}
          </span>
          {email ? (
            <span className="block text-[10px] text-gov-gray-500 font-mono truncate max-w-[12rem]">
              {email}
            </span>
          ) : null}
        </span>
      </div>
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
