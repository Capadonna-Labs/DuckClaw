'use client';

import React, { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore } from '@/store/authStore';
import { Sidebar, Topbar } from '@/components/layout';
import { FloatingAdminChat } from '@/components/chat/FloatingAdminChat';
import { titleForAdminPath } from '@/config/adminNav';
import { useLayoutUiStore } from '@/store/layoutUiStore';
import { Loader2, PanelLeftOpen } from 'lucide-react';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuthStore();
  const router = useRouter();
  const pathname = usePathname();
  const [isSidebarOpen, setIsSidebarOpen] = React.useState(false);
  const { sidebarOpen, setSidebarOpen } = useLayoutUiStore();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace('/login');
    }
    setIsSidebarOpen(false);
  }, [isAuthenticated, isLoading, router, pathname]);

  if (isLoading || !isAuthenticated) {
    return <AdminLoading />;
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
      {!sidebarOpen && (
        <button
          type="button"
          onClick={() => setSidebarOpen(true)}
          className="hidden lg:flex fixed left-0 top-1/2 -translate-y-1/2 z-30 items-center gap-1 px-2 py-3 rounded-r-2xl bg-gov-blue-900 dark:bg-dark-sidebar border border-l-0 border-gov-blue-700 dark:border-dark-border shadow-md text-xs font-bold text-white hover:bg-gov-blue-800"
          title="Mostrar menú lateral"
        >
          <PanelLeftOpen size={18} />
        </button>
      )}
      {isSidebarOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <SidebarOverlay onClose={() => setIsSidebarOpen(false)} />
          <div className="relative flex w-64 flex-col">
            <Sidebar />
          </div>
        </div>
      )}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Topbar title={titleForAdminPath(pathname)} onMenuClick={() => setIsSidebarOpen(true)} />
        <main className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-10">
          <div className="max-w-[1600px] mx-auto">{children}</div>
        </main>
        <FloatingAdminChat />
      </div>
    </div>
  );
}

function AdminLoading() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-4 dark:bg-dark-bg">
      <Loader2 size={32} className="animate-spin text-gov-blue-700" />
      <p className="text-xs font-bold text-gov-gray-400 uppercase tracking-widest">
        Verificando sesión…
      </p>
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
