'use client';

import React, { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore } from '@/store/authStore';
import { Sidebar, Topbar } from '@/components/layout';
import { Loader2 } from 'lucide-react';

const TITLES: Record<string, string> = {
  '/overview': 'Overview',
  '/templates': 'Plantillas',
  '/projects': 'Proyectos',
  '/runtime': 'Runtime',
  '/telegram': 'Telegram',
  '/commands': 'Fly commands',
  '/duckdb': 'DuckDB',
  '/traces': 'Traces',
  '/settings': 'Ajustes',
};

function titleForPath(pathname: string): string {
  for (const [prefix, title] of Object.entries(TITLES)) {
    if (pathname === prefix || pathname.startsWith(`${prefix}/`)) return title;
  }
  return 'DuckClaw Admin';
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading } = useAuthStore();
  const router = useRouter();
  const pathname = usePathname();
  const [isSidebarOpen, setIsSidebarOpen] = React.useState(false);

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
    <div className="flex h-screen overflow-hidden bg-gov-gray-50 dark:bg-dark-bg">
      <div className="hidden lg:flex lg:shrink-0">
        <Sidebar />
      </div>
      {isSidebarOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <SidebarOverlay onClose={() => setIsSidebarOpen(false)} />
          <div className="relative flex w-64 flex-col">
            <Sidebar />
          </div>
        </div>
      )}
      <div className="flex flex-col flex-1 min-w-0 overflow-hidden">
        <Topbar title={titleForPath(pathname)} onMenuClick={() => setIsSidebarOpen(true)} />
        <main className="flex-1 overflow-y-auto p-4 md:p-6 lg:p-10">
          <div className="max-w-[1600px] mx-auto">{children}</div>
        </main>
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
