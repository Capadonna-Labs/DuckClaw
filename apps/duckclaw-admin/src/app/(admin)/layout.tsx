'use client';

import React, { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore } from '@/store/authStore';
import { Sidebar, Topbar } from '@/components/layout';
import { FloatingAdminChat } from '@/components/chat/FloatingAdminChat';
import { useLayoutUiStore } from '@/store/layoutUiStore';
import { Loader2, RefreshCw } from 'lucide-react';
import { cn } from '@/lib/utils';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, hasHydrated, authError, setReturnTo } = useAuthStore();
  const router = useRouter();
  const pathname = usePathname();
  const [isSidebarOpen, setIsSidebarOpen] = React.useState(false);
  const { sidebarOpen } = useLayoutUiStore();
  const isWorkspaceRoute =
    pathname === '/playground' ||
    pathname.startsWith('/sandbox') ||
    pathname === '/kanban';

  useEffect(() => {
    if (!hasHydrated) return;
    if (!isAuthenticated) {
      if (pathname && pathname !== '/login') {
        setReturnTo(pathname);
      }
      router.replace('/login');
    }
    setIsSidebarOpen(false);
  }, [hasHydrated, isAuthenticated, router, pathname, setReturnTo]);

  if (!hasHydrated) {
    return <AdminLoading message="Verificando sesión…" />;
  }

  if (!isAuthenticated) {
    // Errores de gateway (503) sí muestran pantalla de reintento; 401 ya limpia sesión → login.
    if (authError && !/no autenticado|unauthorized/i.test(authError)) {
      return <AdminAuthError message={authError} />;
    }
    return <AdminLoading message="Redirigiendo al login…" />;
  }

  return (
    <div className="flex h-screen overflow-hidden bg-gov-gray-50 dark:bg-dark-bg relative">
      <div
        className={`hidden lg:flex shrink-0 overflow-hidden transition-[width] duration-300 ease-out ${
          sidebarOpen ? 'w-64' : 'w-0'
        }`}
      >
        <Sidebar />
      </div>
      {isSidebarOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <SidebarOverlay onClose={() => setIsSidebarOpen(false)} />
          <div className="relative flex w-64 flex-col">
            <Sidebar onMobileClose={() => setIsSidebarOpen(false)} />
          </div>
        </div>
      )}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Topbar onMenuClick={() => setIsSidebarOpen(true)} />
        <main
          id="admin-main-scroll"
          className={cn(
            'flex-1 max-lg:overscroll-none',
            isWorkspaceRoute
              ? 'overflow-hidden p-2 lg:p-3'
              : 'scrollbar-thin overflow-y-auto p-2 sm:p-4 md:p-6 lg:p-10'
          )}
        >
          <div className={isWorkspaceRoute ? 'h-full w-full min-h-0' : 'max-w-[1600px] mx-auto'}>
            {authError ? (
              <div className="mb-4 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-100">
                {authError} — usando sesión en caché; algunas acciones pueden fallar hasta que el gateway responda.
              </div>
            ) : null}
            {children}
          </div>
        </main>
      </div>
      <FloatingAdminChat />
    </div>
  );
}

function AdminLoading({ message }: { message: string }) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-4 dark:bg-dark-bg px-6 text-center">
      <Loader2 size={32} className="animate-spin text-gov-blue-700" />
      <p className="text-xs font-bold text-gov-gray-400 uppercase tracking-widest">{message}</p>
    </div>
  );
}

function AdminAuthError({ message }: { message: string }) {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-4 dark:bg-dark-bg px-6 text-center max-w-lg mx-auto">
      <p className="text-sm font-semibold text-gov-gray-800 dark:text-dark-text">No se pudo validar la sesión</p>
      <p className="text-sm text-gov-gray-600 dark:text-dark-muted">{message}</p>
      <div className="flex flex-wrap justify-center gap-3">
        <button
          type="button"
          onClick={() => window.location.reload()}
          className="inline-flex items-center gap-2 rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-bold text-white"
        >
          <RefreshCw size={16} />
          Reintentar
        </button>
        <a
          href="/login"
          className="rounded-xl border border-gov-gray-200 px-4 py-2 text-sm font-bold text-gov-gray-800 dark:border-dark-border dark:text-dark-text"
        >
          Ir al login
        </a>
      </div>
    </div>
  );
}

function SidebarOverlay({ onClose }: { onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 bg-gov-blue-900/60 backdrop-blur-sm"
      onClick={onClose}
      role="presentation"
    />
  );
}
