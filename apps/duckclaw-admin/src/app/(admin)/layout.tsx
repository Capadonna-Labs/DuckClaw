'use client';

import React, { useEffect } from 'react';
import { useRouter, usePathname } from 'next/navigation';
import { useAuthStore } from '@/store/authStore';
import { Sidebar, Topbar } from '@/components/layout';
import { FloatingAdminChat } from '@/components/chat/FloatingAdminChat';
import { useLayoutUiStore } from '@/store/layoutUiStore';
import { Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, hasHydrated, setReturnTo } = useAuthStore();
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

  if (!hasHydrated || !isAuthenticated) {
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
              : 'overflow-y-auto p-2 sm:p-4 md:p-6 lg:p-10'
          )}
        >
          <div className={isWorkspaceRoute ? 'h-full w-full min-h-0' : 'max-w-[1600px] mx-auto'}>
            {children}
          </div>
        </main>
      </div>
      <FloatingAdminChat />
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
