'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import {
  LayoutDashboard,
  Bot,
  Database,
  MessageSquare,
  Settings,
  Activity,
  FolderPlus,
  Radio,
  LogOut,
  Terminal,
  ClipboardList,
  Blocks,
  Cable,
  RefreshCw,
  LayoutGrid,
  MessageCircle,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import { useLayoutUiStore } from '@/store/layoutUiStore';
import { PanelToggleButton } from '@/components/layout/PanelToggleButton';
import { navItemsForRole } from '@/config/adminNav';
import { cn } from '@/lib/utils';
import type { LucideIcon } from 'lucide-react';

const NAV_ICONS: Record<string, LucideIcon> = {
  '/overview': LayoutDashboard,
  '/kanban': LayoutGrid,
  '/templates': Bot,
  '/skills': Blocks,
  '/mcp': Cable,
  '/projects/new': FolderPlus,
  '/playground': MessageCircle,
  '/runtime': Radio,
  '/telegram': MessageSquare,
  '/commands': Terminal,
  '/duckdb': Database,
  '/traces': Activity,
  '/ops': RefreshCw,
  '/audit': ClipboardList,
  '/settings': Settings,
};

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { usuario, logout } = useAuthStore();
  const { sidebarOpen, toggleSidebar } = useLayoutUiStore();

  const nav = navItemsForRole(usuario?.rol === 'admin').map((item) => ({
    ...item,
    icon: NAV_ICONS[item.href] ?? LayoutDashboard,
  }));

  const handleLogout = () => {
    logout();
    router.replace('/login');
  };

  return (
    <nav
      className="flex flex-col h-full w-64 bg-gov-blue-900 border-r border-gov-blue-700 shrink-0 dark:bg-dark-sidebar dark:border-dark-border"
      aria-label="Navegación principal"
    >
      <div className="p-4 md:p-6 border-b border-gov-blue-700 dark:border-dark-border space-y-3">
        <div className="flex items-center gap-3">
          <BrandIcon />
          <BrandTitles />
        </div>
        <PanelToggleButton
          open={sidebarOpen}
          onToggle={toggleSidebar}
          openLabel="Ocultar menú"
          closedLabel="Mostrar menú"
          openIcon={PanelLeftClose}
          closedIcon={PanelLeftOpen}
          title={sidebarOpen ? 'Ocultar menú lateral' : 'Mostrar menú lateral'}
          className="w-full justify-center border-white/20 text-white/90 hover:bg-white/10 hover:text-white"
        />
      </div>
      <div className="flex-1 px-3 py-3 space-y-1 overflow-y-auto">
        {nav.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              'flex items-center gap-3 px-4 py-2.5 text-sm font-medium rounded-lg transition-colors',
              pathname === href || pathname.startsWith(`${href}/`)
                ? 'bg-gov-blue-700 text-white'
                : 'text-gov-gray-300 hover:bg-gov-blue-700/40 hover:text-white'
            )}
          >
            <Icon size={20} />
            {label}
          </Link>
        ))}
      </div>
      <footer className="p-4 border-t border-gov-blue-700 dark:border-dark-border space-y-3">
        <div className="px-2">
          <p className="text-gov-cyan-400 text-xs font-semibold truncate">{usuario?.email}</p>
          <p className="text-gov-gray-500 text-[10px] capitalize">rol: {usuario?.rol}</p>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-semibold text-white/90 bg-gov-blue-800 hover:bg-red-700 rounded-lg transition-colors"
        >
          <LogOut size={18} />
          Cerrar sesión
        </button>
      </footer>
    </nav>
  );
}

function BrandIcon() {
  return (
    <div className="w-10 h-10 rounded-lg bg-white/10 flex items-center justify-center text-xl">
      🦆
    </div>
  );
}

function BrandTitles() {
  return (
    <div>
      <h1 className="text-white font-bold text-sm">DuckClaw</h1>
      <p className="text-gov-cyan-400 text-[10px] font-bold uppercase tracking-wider">Admin</p>
    </div>
  );
}
