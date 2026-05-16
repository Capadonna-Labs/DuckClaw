'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  LayoutDashboard,
  Bot,
  Database,
  MessageSquare,
  Settings,
  Activity,
  FolderPlus,
  Radio,
} from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import { cn } from '@/lib/utils';

const NAV = [
  { href: '/overview', label: 'Overview', icon: LayoutDashboard },
  { href: '/templates', label: 'Plantillas', icon: Bot },
  { href: '/projects/new', label: 'Nuevo proyecto', icon: FolderPlus },
  { href: '/runtime', label: 'Runtime', icon: Radio },
  { href: '/telegram', label: 'Telegram', icon: MessageSquare },
  { href: '/duckdb', label: 'DuckDB', icon: Database },
  { href: '/traces', label: 'Traces', icon: Activity },
  { href: '/settings', label: 'Ajustes', icon: Settings },
] as const;

export default function Sidebar() {
  const pathname = usePathname();
  const { usuario } = useAuthStore();

  return (
    <nav
      className="flex flex-col h-full w-64 bg-gov-blue-900 border-r border-gov-blue-700 shrink-0 dark:bg-dark-sidebar dark:border-dark-border"
      aria-label="Navegación principal"
    >
      <div className="p-4 md:p-6">
        <div className="flex items-center gap-3 mb-6">
          <div className="flex items-center justify-center w-10 h-10 bg-white/10 rounded-lg text-2xl">
            🦆
          </div>
          <motionTitlesBlock />
        </div>
        <div className="border-b border-gov-blue-700 dark:border-dark-border" />
      </div>
      <div className="flex-1 px-3 md:px-4 space-y-1 overflow-y-auto py-2">
        {NAV.map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className={cn(
              'flex items-center gap-3 px-4 py-2.5 text-sm font-medium transition-colors rounded-lg',
              pathname === href || pathname.startsWith(`${href}/`)
                ? 'bg-gov-blue-700 text-white'
                : 'text-gov-gray-300 hover:bg-gov-blue-700/40 hover:text-white'
            )}
          >
            <Icon size={20} />
            <span>{label}</span>
          </Link>
        ))}
      </div>
      <footer className="p-4 md:p-6 mt-auto space-y-2">
        <p className="text-gov-cyan-400 text-xs font-semibold truncate">{usuario?.email}</p>
        <p className="text-gov-gray-500 text-[10px] dark:text-dark-muted capitalize">
          rol: {usuario?.rol ?? '—'}
        </p>
        <p className="text-gov-gray-500 text-[10px] dark:text-dark-muted">DuckClaw Admin</p>
      </footer>
    </nav>
  );
}

function motionTitlesBlock() {
  return (
    <div className="min-w-0">
      <h1 className="text-white font-bold text-sm leading-tight truncate">DuckClaw</h1>
      <p className="text-gov-cyan-400 text-[10px] font-bold uppercase tracking-wider truncate">
        Admin Console
      </p>
    </div>
  );
}
