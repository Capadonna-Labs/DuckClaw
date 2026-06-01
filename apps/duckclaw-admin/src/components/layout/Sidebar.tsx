'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
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
  Image,
  Sparkles,
  Hammer,
  ServerCog,
  ShieldCheck,
  Monitor,
  UserCircle,
} from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import {
  navEntriesForRole,
  type AdminNavGroup,
  type AdminNavItem,
} from '@/config/adminNav';
import { cn } from '@/lib/utils';
import type { LucideIcon } from 'lucide-react';

const NAV_ICONS: Record<string, LucideIcon> = {
  '/overview': LayoutDashboard,
  '/kanban': LayoutGrid,
  '/templates': Bot,
  '/projects': FolderPlus,
  '/skills': Blocks,
  '/mcp': Cable,
  '/projects/new': FolderPlus,
  '/playground': MessageCircle,
  '/integrations': Cable,
  '/gen/image': Image,
  '/runtime': Radio,
  '/telegram': MessageSquare,
  '/integrations/edge-devices': Cpu,
  '/vnc': Monitor,
  '/duckdb': Database,
  '/train': GraduationCap,
  '/admin/access': ShieldCheck,
  '/audit': ClipboardList,
  '/settings': Settings,
};

const GROUP_ICONS: Record<string, LucideIcon> = {
  'user-workspace': UserCircle,
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
  if (group.id === 'playground') {
    return pathname.startsWith('/playground') || pathname === '/kanban';
  }
  return group.items.some((item) => {
    if (item.href === '/integrations') {
      return pathname === '/telegram' || pathname.startsWith('/integrations');
    }
    return isNavActive(pathname, item.href);
  });
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
  const [openGroupId, setOpenGroupId] = useState<string | null>('operation');

  useEffect(() => {
    const activeGroup = entries.find(
      (entry) => entry.type === 'group' && groupHasActive(pathname, entry.group)
    );
    if (activeGroup?.type === 'group') {
      setOpenGroupId(activeGroup.group.id);
    }
  }, [entries, pathname]);

  return (
    <nav
      className="flex flex-col h-full min-h-0 w-64 bg-gov-blue-900 border-r border-gov-blue-700 shrink-0 dark:bg-dark-sidebar dark:border-dark-border"
      aria-label="Navegación principal"
    >
      <div className="p-4 md:p-5 border-b border-gov-blue-700 dark:border-dark-border space-y-3 shrink-0">
        <div className="flex items-center gap-3">
          <BrandIcon />
          <BrandTitles />
        </div>
      </div>
      <div className="flex-1 min-h-0 px-3 py-3 space-y-3 overflow-y-auto">
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
    </nav>
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
  const active = groupHasActive(pathname, group);

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
      {open && (
        <div className="space-y-0.5">
          {group.items.map((item) => {
            const Icon = NAV_ICONS[item.href] ?? LayoutDashboard;
            const childActive = isNavActive(pathname, item.href);
            if (item.href === '/playground') {
              return (
                <PlaygroundNavSelector
                  key={item.href}
                  item={item}
                  icon={Icon}
                  active={childActive || pathname === '/kanban'}
                  onNavigate={onNavigate}
                />
              );
            }
            if (item.href === '/integrations') {
              return (
                <IntegrationsNavSelector
                  key={item.href}
                  item={item}
                  icon={Icon}
                  active={pathname === '/telegram' || pathname.startsWith('/integrations')}
                  onNavigate={onNavigate}
                />
              );
            }
            return (
              <Link
                key={item.href}
                href={item.href}
                onClick={() => onNavigate?.()}
                className={cn(
                  'flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-xl transition-colors',
                  childActive
                    ? 'bg-white text-gov-blue-900 shadow-sm dark:bg-dark-surface dark:text-dark-text'
                    : 'text-gov-gray-300 hover:bg-gov-blue-700/40 hover:text-white'
                )}
              >
                <Icon size={18} />
                {item.label}
              </Link>
            );
          })}
        </div>
      )}
    </section>
  );
}

function IntegrationsNavSelector({
  item,
  icon: Icon,
  active,
  onNavigate,
}: {
  item: AdminNavItem;
  icon: LucideIcon;
  active: boolean;
  onNavigate?: () => void;
}) {
  const [open, setOpen] = useState(active);

  useEffect(() => {
    if (active) setOpen(true);
  }, [active]);

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className={cn(
          'w-full flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-xl transition-colors',
          active
            ? 'bg-white text-gov-blue-900 shadow-sm dark:bg-dark-surface dark:text-dark-text'
            : 'text-gov-gray-300 hover:bg-gov-blue-700/40 hover:text-white'
        )}
      >
        <Icon size={18} />
        <span className="flex-1 text-left">{item.label}</span>
        <ChevronDown size={14} className={cn('shrink-0 transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="ml-7 mt-1 space-y-0.5 border-l border-white/10 pl-3">
          <Link
            href="/telegram"
            onClick={() => onNavigate?.()}
            className="block rounded-lg px-2 py-1.5 text-xs font-semibold text-gov-gray-300 hover:bg-gov-blue-700/40 hover:text-white"
          >
            Telegram
          </Link>
          <Link
            href="/integrations/edge-devices"
            onClick={() => onNavigate?.()}
            className="block rounded-lg px-2 py-1.5 text-xs font-semibold text-gov-gray-300 hover:bg-gov-blue-700/40 hover:text-white"
          >
            Edge devices
          </Link>
        </div>
      )}
    </div>
  );
}

function PlaygroundNavSelector({
  item,
  icon: Icon,
  active,
  onNavigate,
}: {
  item: AdminNavItem;
  icon: LucideIcon;
  active: boolean;
  onNavigate?: () => void;
}) {
  const [open, setOpen] = useState(active);

  useEffect(() => {
    if (active) setOpen(true);
  }, [active]);

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className={cn(
          'w-full flex items-center gap-3 px-3 py-2 text-sm font-medium rounded-xl transition-colors',
          active
            ? 'bg-white text-gov-blue-900 shadow-sm dark:bg-dark-surface dark:text-dark-text'
            : 'text-gov-gray-300 hover:bg-gov-blue-700/40 hover:text-white'
        )}
      >
        <Icon size={18} />
        <span className="flex-1 text-left">{item.label}</span>
        <ChevronDown size={14} className={cn('shrink-0 transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="ml-7 mt-1 space-y-0.5 border-l border-white/10 pl-3">
          <Link
            href="/playground?view=history"
            onClick={() => onNavigate?.()}
            className="block rounded-lg px-2 py-1.5 text-xs font-semibold text-gov-gray-300 hover:bg-gov-blue-700/40 hover:text-white"
          >
            Historial
          </Link>
          <Link
            href="/kanban"
            onClick={() => onNavigate?.()}
            className="block rounded-lg px-2 py-1.5 text-xs font-semibold text-gov-gray-300 hover:bg-gov-blue-700/40 hover:text-white"
          >
            Tablero
          </Link>
          <Link
            href="/playground?new=1"
            onClick={() => onNavigate?.()}
            className="block rounded-lg px-2 py-1.5 text-xs font-semibold text-gov-gray-300 hover:bg-gov-blue-700/40 hover:text-white"
          >
            Nueva conversación
          </Link>
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
