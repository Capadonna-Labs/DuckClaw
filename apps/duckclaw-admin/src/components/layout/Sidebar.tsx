'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
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
  ChevronDown,
  Plug,
  Cpu,
} from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import { useLayoutUiStore } from '@/store/layoutUiStore';
import { PanelToggleButton } from '@/components/layout/PanelToggleButton';
import { navEntriesForRole, type AdminNavGroup, type AdminNavItem } from '@/config/adminNav';
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
  '/integrations/edge-devices': Cpu,
  '/commands': Terminal,
  '/duckdb': Database,
  '/traces': Activity,
  '/ops': RefreshCw,
  '/audit': ClipboardList,
  '/settings': Settings,
};

function isNavActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function groupHasActive(pathname: string, group: AdminNavGroup): boolean {
  return group.items.some((item) => isNavActive(pathname, item.href));
}

export default function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const { usuario, logout } = useAuthStore();
  const { sidebarOpen, toggleSidebar } = useLayoutUiStore();
  const entries = navEntriesForRole(usuario?.rol === 'admin');
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() => ({
    integrations:
      pathname.startsWith('/telegram') || pathname.startsWith('/integrations'),
  }));

  useEffect(() => {
    if (pathname.startsWith('/telegram') || pathname.startsWith('/integrations')) {
      setOpenGroups((prev) => ({ ...prev, integrations: true }));
    }
  }, [pathname]);

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
        {entries.map((entry) => {
          if (entry.type === 'item') {
            return (
              <NavLink
                key={entry.item.href}
                item={entry.item}
                pathname={pathname}
                icon={NAV_ICONS[entry.item.href] ?? LayoutDashboard}
              />
            );
          }
          return (
            <NavGroup
              key={entry.group.id}
              group={entry.group}
              pathname={pathname}
              open={openGroups[entry.group.id] ?? false}
              onToggle={() =>
                setOpenGroups((prev) => ({
                  ...prev,
                  [entry.group.id]: !prev[entry.group.id],
                }))
              }
              groupIcon={Plug}
            />
          );
        })}
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

function NavLink({
  item,
  pathname,
  icon: Icon,
}: {
  item: AdminNavItem;
  pathname: string;
  icon: LucideIcon;
}) {
  const active = isNavActive(pathname, item.href);
  return (
    <Link
      href={item.href}
      className={cn(
        'flex items-center gap-3 px-4 py-2.5 text-sm font-medium rounded-lg transition-colors',
        active
          ? 'bg-gov-blue-700 text-white'
          : 'text-gov-gray-300 hover:bg-gov-blue-700/40 hover:text-white'
      )}
    >
      <Icon size={20} />
      {item.label}
    </Link>
  );
}

function NavGroup({
  group,
  pathname,
  open,
  onToggle,
  groupIcon: GroupIcon,
}: {
  group: AdminNavGroup;
  pathname: string;
  open: boolean;
  onToggle: () => void;
  groupIcon: LucideIcon;
}) {
  const active = groupHasActive(pathname, group);

  return (
    <div className="space-y-0.5">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className={cn(
          'w-full flex items-center gap-3 px-4 py-2.5 text-sm font-medium rounded-lg transition-colors',
          active
            ? 'bg-gov-blue-700/60 text-white'
            : 'text-gov-gray-300 hover:bg-gov-blue-700/40 hover:text-white'
        )}
      >
        <GroupIcon size={20} />
        <span className="flex-1 text-left">{group.label}</span>
        <ChevronDown
          size={16}
          className={cn('shrink-0 transition-transform', open && 'rotate-180')}
        />
      </button>
      {open && (
        <div className="ml-3 pl-3 border-l border-white/10 space-y-0.5">
          {group.items.map((item) => {
            const Icon = NAV_ICONS[item.href] ?? LayoutDashboard;
            const childActive = isNavActive(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={cn(
                  'flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-lg transition-colors',
                  childActive
                    ? 'bg-gov-blue-700 text-white'
                    : 'text-gov-gray-400 hover:bg-gov-blue-700/40 hover:text-white'
                )}
              >
                <Icon size={18} />
                {item.label}
              </Link>
            );
          })}
        </div>
      )}
    </div>
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
