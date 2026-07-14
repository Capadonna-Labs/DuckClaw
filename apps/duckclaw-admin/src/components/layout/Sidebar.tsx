'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Suspense, useEffect, useMemo, useState } from 'react';
import {
  LayoutDashboard,
  Bot,
  Database,
  MessageSquare,
  Settings,
  GraduationCap,
  FolderPlus,
  Radio,
  ClipboardList,
  Blocks,
  Cable,
  LayoutGrid,
  MessageCircle,
  ChevronDown,
  Cpu,
  Mic,
  Image,
  Sparkles,
  Hammer,
  ServerCog,
  ShieldCheck,
  Monitor,
  UserCircle,
  Box,
  LogOut,
} from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import {
  navEntriesForRole,
  type AdminNavGroup,
  type AdminNavItem,
} from '@/config/adminNav';
import { pathnameMatchesHub } from '@/lib/adminHubRoutes';
import { IntegracionesNavSelector } from '@/components/layout/IntegracionesNavSelector';
import { PlataformaNavSelector } from '@/components/layout/PlataformaNavSelector';
import { cn } from '@/lib/utils';
import type { LucideIcon } from 'lucide-react';

const NAV_ICONS: Record<string, LucideIcon> = {
  '/productividad': ClipboardList,
  '/plataforma': ServerCog,
  '/integraciones': Cable,
  '/administracion': ShieldCheck,
  '/reports': ClipboardList,
  '/overview': LayoutDashboard,
  '/kanban': LayoutGrid,
  '/templates': Bot,
  '/projects': FolderPlus,
  '/knowledge': Database,
  '/policies': ClipboardList,
  '/skills': Blocks,
  '/mcp': Cable,
  '/playground': MessageCircle,
  '/sandbox': Box,
  '/integrations': Cable,
  '/gen/image': Image,
  '/runtime': Radio,
  '/telegram': MessageSquare,
  '/integrations/edge-devices': Cpu,
  '/integrations/sensory-node': Mic,
  '/vnc': Monitor,
  '/duckdb': Database,
  '/train': GraduationCap,
  '/admin/access': ShieldCheck,
  '/audit': ClipboardList,
  '/settings': Settings,
};

const GROUP_ICONS: Record<string, LucideIcon> = {
  primary: LayoutDashboard,
  more: Sparkles,
  'user-workspace': UserCircle,
  work: MessageCircle,
  studio: Hammer,
  platform: ServerCog,
  conversar: MessageCircle,
  operation: LayoutDashboard,
  playground: MessageCircle,
  build: Hammer,
  data: ServerCog,
  integrations: Cable,
  security: ShieldCheck,
  system: Settings,
};

function isNavActive(pathname: string, href: string): boolean {
  return pathname === href || pathname.startsWith(`${href}/`);
}

function groupHasActive(pathname: string, group: AdminNavGroup): boolean {
  if (group.id === 'primary') {
    return (
      pathname === '/overview' ||
      pathname.startsWith('/playground') ||
      pathname.startsWith('/templates') ||
      pathname.startsWith('/knowledge')
    );
  }
  return group.items.some((item) => pathnameMatchesHub(pathname, item.href));
}

type SidebarProps = {
  /** Cierra el drawer móvil (overlay). En desktop no se pasa. */
  onMobileClose?: () => void;
};

export default function Sidebar({ onMobileClose }: SidebarProps = {}) {
  const pathname = usePathname();
  const { usuario } = useAuthStore();
  const entries = useMemo(
    () => navEntriesForRole(usuario?.rol),
    [usuario?.rol]
  );
  const [openGroupId, setOpenGroupId] = useState<string | null>(null);

  useEffect(() => {
    const activeMore = entries.find(
      (entry) => entry.type === 'group' && entry.group.id === 'more' && groupHasActive(pathname, entry.group)
    );
    if (activeMore?.type === 'group') {
      setOpenGroupId('more');
    }
  }, [entries, pathname]);

  return (
    <nav
      className="flex flex-col h-full min-h-0 w-64 bg-gov-blue-900 border-r border-gov-blue-700 shrink-0 dark:bg-dark-sidebar dark:border-dark-border"
      aria-label="Navegación principal"
    >
      <div className="h-16 px-4 md:px-5 border-b border-gov-blue-700 dark:border-dark-border flex items-center shrink-0">
        <div className="flex items-center gap-3">
          <BrandIcon />
          <BrandTitles />
        </div>
      </div>
      <div className="flex-1 min-h-0 px-3 py-3 space-y-3 overflow-y-auto scrollbar-thin">
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
              open={openGroupId === entry.group.id}
              onToggle={() =>
                setOpenGroupId((current) => (current === entry.group.id ? null : entry.group.id))
              }
              groupIcon={GROUP_ICONS[entry.group.id] ?? Sparkles}
              onNavigate={onMobileClose}
            />
          );
        })}
      </div>
      <SidebarFooter onMobileClose={onMobileClose} />
    </nav>
  );
}

function SidebarFooter({ onMobileClose }: { onMobileClose?: () => void }) {
  const router = useRouter();
  const { logout } = useAuthStore();

  const handleLogout = () => {
    logout();
    onMobileClose?.();
    router.replace('/login');
  };

  return (
    <div className="shrink-0 border-t border-gov-blue-700 px-3 py-3 dark:border-dark-border">
      <button
        type="button"
        onClick={handleLogout}
        className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-sm font-semibold text-red-300 transition-colors hover:bg-gov-blue-700/50 hover:text-red-200"
      >
        <LogOut size={18} />
        Cerrar sesión
      </button>
    </div>
  );
}

function NavLink({
  item,
  pathname,
  icon: Icon,
  onNavigate,
}: {
  item: AdminNavItem;
  pathname: string;
  icon: LucideIcon;
  onNavigate?: () => void;
}) {
  const active = isNavActive(pathname, item.href);
  return (
    <Link
      href={item.href}
      onClick={() => onNavigate?.()}
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
  onNavigate,
}: {
  group: AdminNavGroup;
  pathname: string;
  open: boolean;
  onToggle: () => void;
  groupIcon: LucideIcon;
  onNavigate?: () => void;
}) {
  const collapsible = group.collapsible !== false;
  const active = groupHasActive(pathname, group);

  const renderItem = (item: AdminNavItem) => {
    const Icon = NAV_ICONS[item.href] ?? LayoutDashboard;
    const childActive = pathnameMatchesHub(pathname, item.href);

    if (item.href === '/plataforma') {
      return (
        <Suspense key={`${item.href}-${item.label}`} fallback={null}>
          <PlataformaNavSelector icon={Icon} label={item.label} onNavigate={onNavigate} />
        </Suspense>
      );
    }

    if (item.href === '/integraciones') {
      return (
        <Suspense key={`${item.href}-${item.label}`} fallback={null}>
          <IntegracionesNavSelector icon={Icon} label={item.label} onNavigate={onNavigate} />
        </Suspense>
      );
    }

    return (
      <Link
        key={`${item.href}-${item.label}`}
        href={item.href}
        onClick={() => onNavigate?.()}
        className={cn(
          collapsible
            ? 'flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-xl transition-colors'
            : 'flex items-center gap-3 px-4 py-2.5 text-sm font-medium rounded-lg transition-colors',
          childActive
            ? collapsible
              ? 'bg-white text-gov-blue-900 shadow-sm dark:bg-dark-surface dark:text-dark-text'
              : 'bg-gov-blue-700 text-white'
            : collapsible
              ? 'text-gov-gray-300 hover:bg-gov-blue-700/40 hover:text-white'
              : 'text-gov-gray-300 hover:bg-gov-blue-700/40 hover:text-white'
        )}
      >
        <Icon size={collapsible ? 18 : 20} />
        {item.label}
      </Link>
    );
  };

  if (!collapsible) {
    return <div className="space-y-0.5">{group.items.map((item) => renderItem(item))}</div>;
  }

  return (
    <section className="space-y-1">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className={cn(
          'w-full flex items-center gap-2 px-2 py-1.5 text-xs font-black uppercase tracking-wide rounded-xl transition-colors',
          active
            ? 'text-white'
            : 'text-gov-gray-300 hover:bg-gov-blue-700/30 hover:text-white'
        )}
      >
        <GroupIcon size={15} />
        <span className="flex-1 text-left">{group.label}</span>
        <ChevronDown
          size={16}
          className={cn('shrink-0 transition-transform', open && 'rotate-180')}
        />
      </button>
      {open && <div className="space-y-0.5">{group.items.map((item) => renderItem(item))}</div>}
    </section>
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
