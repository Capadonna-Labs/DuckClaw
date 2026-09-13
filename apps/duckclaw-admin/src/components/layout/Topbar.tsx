'use client';

import { Menu, Moon, RefreshCw, Sparkles, Sun, X } from 'lucide-react';
import { useLayoutUiStore } from '@/store/layoutUiStore';
import { usePathname } from 'next/navigation';
import { useAuthStore } from '@/store/authStore';
import { obtenerIniciales } from '@/lib/utils';
import { useTheme } from '@/components/shared/ThemeProvider';
import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { adminService } from '@/services/adminService';
import { formatOpsOutput } from '@/lib/formatOpsOutput';
import { PlatformStatusStrip } from '@/components/admin/GatewayStatusBadge';
import { UpdateBanner } from '@/components/layout/UpdateBanner';
import { markStackReloadPending } from '@/lib/playgroundLastSelection';
import { useGatewayHealthStore } from '@/store/gatewayHealthStore';
import { writeAuthSnapshot } from '@/lib/authSessionCache';
import {
  isUnauthorizedDetail,
  redirectToLoginOnUnauthorized,
} from '@/lib/sessionExpired';

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
  const [portalReady, setPortalReady] = useState(false);

  useEffect(() => {
    setPortalReady(true);
  }, []);

  useEffect(() => {
    if (!stackRestartMessage?.startsWith('Stack recuperado')) return;
    markStackReloadPending();
    // Lite/desktop: el store en memoria se vacía al reiniciar. No reusar snapshot.
    writeAuthSnapshot(null);
    let cancelled = false;
    const timer = window.setTimeout(() => {
      void (async () => {
        try {
          const res = await fetch('/api/admin/auth/me', {
            credentials: 'include',
            cache: 'no-store',
          });
          if (cancelled) return;
          if (!res.ok) {
            redirectToLoginOnUnauthorized();
            return;
          }
          window.location.reload();
        } catch {
          if (!cancelled) redirectToLoginOnUnauthorized();
        }
      })();
    }, 1500);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
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
          ? 'Stack recuperado: migraciones + PM2. Comprobando sesión…'
          : 'Migraciones y PM2 OK, pero /health no respondió aún. Espera 30s y recarga manualmente.'
      );
    } catch (e) {
      const msg = e instanceof Error ? e.message : 'No se pudo reiniciar el stack';
      if (isUnauthorizedDetail(msg)) {
        redirectToLoginOnUnauthorized();
        return;
      }
      setStackRestartMessage(msg);
    } finally {
      useGatewayHealthStore.getState().endRecovery();
      await useGatewayHealthStore.getState().refresh(true);
      setStackRestarting(false);
    }
  };

  return (
    <>
      <UpdateBanner />
      <header
      role="banner"
      className={`h-16 shrink-0 px-4 md:px-6 flex items-center justify-between backdrop-blur-xl backdrop-saturate-150 ${
        isChatTab
          ? 'border-b-0 bg-white/70 dark:bg-dark-surface/70 supports-[backdrop-filter]:bg-white/55 dark:supports-[backdrop-filter]:bg-dark-surface/55'
          : 'border-b border-white/40 bg-white/80 dark:border-white/10 dark:bg-dark-surface/80 supports-[backdrop-filter]:bg-white/65 dark:supports-[backdrop-filter]:bg-dark-surface/65'
      }`}
    >
      <TopbarLeft
        onMenuClick={handleMenuToggle}
        sidebarOpen={sidebarOpen}
      />
      <div className="flex items-center gap-2 md:gap-4">
        <div className="flex items-center gap-2">
          <PlatformStatusStrip />
          {canRunOps && (
            <button
              type="button"
              onClick={() => void restartStack()}
              disabled={stackRestarting}
              className="inline-flex min-h-[36px] items-center gap-1.5 rounded-xl border border-gov-blue-100 px-2.5 py-2 text-xs font-bold text-gov-blue-800 hover:bg-gov-blue-50 disabled:opacity-50 dark:border-dark-border dark:text-dark-cyan dark:hover:bg-dark-bg"
              title="Detiene PM2, libera locks DuckDB, migra y relanza gateway/db-writer/heartbeat"
              aria-label={stackRestarting ? 'Reiniciando sistema' : 'Reiniciar sistema'}
            >
              <RefreshCw size={17} className={stackRestarting ? 'animate-spin' : ''} />
              <span className="hidden sm:inline whitespace-nowrap">
                {stackRestarting ? 'Reiniciando…' : 'Reiniciar sistema'}
              </span>
            </button>
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
      {portalReady &&
        (stackRestartMessage || stackRestarting) &&
        createPortal(
          <div
            className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/45 px-4"
            style={{
              paddingTop: 'env(safe-area-inset-top, 0px)',
              paddingBottom: 'env(safe-area-inset-bottom, 0px)',
            }}
            data-stack-restart-toast="true"
          >
            <div
              role="status"
              aria-live="assertive"
              className="flex w-full max-w-md items-start gap-2 rounded-2xl border-2 border-amber-400 bg-amber-50 p-4 text-sm font-semibold text-amber-950 shadow-2xl dark:border-amber-500 dark:bg-amber-950 dark:text-amber-50"
            >
              <p className="min-w-0 flex-1 whitespace-pre-wrap">
                {stackRestartMessage ?? 'Reiniciando sistema…'}
              </p>
              {!stackRestarting && (
                <button
                  type="button"
                  onClick={() => setStackRestartMessage(null)}
                  className="shrink-0 rounded-lg p-1 text-amber-800/70 hover:bg-amber-200/80 hover:text-amber-950 dark:text-amber-100/80 dark:hover:bg-amber-900 dark:hover:text-amber-50"
                  aria-label="Cerrar aviso"
                >
                  <X size={16} />
                </button>
              )}
            </div>
          </div>,
          document.body
        )}
    </>
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
