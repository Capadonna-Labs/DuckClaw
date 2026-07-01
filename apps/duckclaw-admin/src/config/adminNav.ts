/** Fuente única de rutas del panel admin (Sidebar + Topbar). */
import type { AdminRole } from '@/types/admin';
import { isAdminRole } from '@/lib/roles';

export type NavSection = 'core' | 'integrations' | 'admin' | 'footer';
export type NavAudience = 'all' | 'user' | 'admin';

export type AdminNavItem = {
  href: string;
  label: string;
  section: NavSection;
  audience?: NavAudience;
  /** Solo visible si usuario.rol === 'admin' */
  adminOnly?: boolean;
};

export type AdminNavGroup = {
  id: string;
  label: string;
  hint?: string;
  /** Si false, los ítems se muestran siempre sin acordeón (p. ej. navegación principal). */
  collapsible?: boolean;
  items: readonly AdminNavItem[];
};

export type AdminNavEntry =
  | { type: 'item'; item: AdminNavItem }
  | { type: 'group'; group: AdminNavGroup };

/** 4 destinos visibles: Inicio, Chat, Agentes, Conocimiento. */
export const PRIMARY_NAV_GROUP: AdminNavGroup = {
  id: 'primary',
  label: 'Principal',
  collapsible: false,
  items: [
    { href: '/overview', label: 'Inicio', section: 'core', audience: 'all' },
    { href: '/playground', label: 'Chat', section: 'core', audience: 'all' },
    { href: '/templates', label: 'Agentes', section: 'core', audience: 'admin' },
    { href: '/templates', label: 'Mis agentes', section: 'core', audience: 'user' },
    { href: '/knowledge', label: 'Conocimiento', section: 'core', audience: 'all' },
  ],
};

/** Proyectos, plataforma y operación avanzada (colapsado por defecto). */
export const MORE_NAV_GROUP: AdminNavGroup = {
  id: 'more',
  label: 'Más',
  hint: 'Proyectos, hubs y avanzado',
  collapsible: true,
  items: [
    { href: '/projects', label: 'Proyectos', section: 'core', audience: 'all' },
    { href: '/sandbox', label: 'Sandbox', section: 'core', audience: 'all' },
    { href: '/productividad', label: 'Productividad', section: 'core', audience: 'admin' },
    { href: '/plataforma', label: 'Plataforma', section: 'core', audience: 'admin' },
    { href: '/integraciones', label: 'Integraciones', section: 'integrations', audience: 'admin' },
    {
      href: '/administracion',
      label: 'Administración',
      section: 'admin',
      audience: 'admin',
      adminOnly: true,
    },
  ],
};

/** @deprecated aliases — tests e imports legacy */
export const USER_WORKSPACE_NAV_GROUP = PRIMARY_NAV_GROUP;
export const WORK_NAV_GROUP = PRIMARY_NAV_GROUP;
export const STUDIO_NAV_GROUP = MORE_NAV_GROUP;
export const PLATFORM_NAV_GROUP = MORE_NAV_GROUP;
export const CONVERSAR_NAV_GROUP = PRIMARY_NAV_GROUP;
export const BUILD_NAV_GROUP = MORE_NAV_GROUP;
export const DATA_NAV_GROUP = MORE_NAV_GROUP;
export const OPERATION_NAV_GROUP = MORE_NAV_GROUP;
export const PLAYGROUND_NAV_GROUP = PRIMARY_NAV_GROUP;
export const INTEGRATIONS_NAV_GROUP = MORE_NAV_GROUP;
export const SECURITY_NAV_GROUP = MORE_NAV_GROUP;
export const SYSTEM_NAV_GROUP = MORE_NAV_GROUP;

export const USER_NAV_STRUCTURE: readonly AdminNavEntry[] = [
  { type: 'group', group: PRIMARY_NAV_GROUP },
  { type: 'group', group: MORE_NAV_GROUP },
];

export const ADMIN_NAV_STRUCTURE: readonly AdminNavEntry[] = [
  { type: 'group', group: PRIMARY_NAV_GROUP },
  { type: 'group', group: MORE_NAV_GROUP },
];

export const ADMIN_NAV: readonly AdminNavItem[] = [
  ...PRIMARY_NAV_GROUP.items,
  ...MORE_NAV_GROUP.items,
];

function itemVisible(item: AdminNavItem, role: AdminRole | undefined): boolean {
  const isAdmin = isAdminRole(role);
  if (item.adminOnly && !isAdmin) return false;
  if (item.audience === 'admin') return isAdmin;
  if (item.audience === 'user') return !isAdmin;
  return true;
}

function visibleGroupItems(group: AdminNavGroup, role: AdminRole | undefined): AdminNavItem[] {
  return group.items.filter((item) => itemVisible(item, role));
}

export function navEntriesForRole(role: AdminRole | undefined): AdminNavEntry[] {
  const structure = isAdminRole(role) ? ADMIN_NAV_STRUCTURE : USER_NAV_STRUCTURE;
  const out: AdminNavEntry[] = [];
  for (const entry of structure) {
    if (entry.type === 'item') {
      if (itemVisible(entry.item, role)) out.push(entry);
      continue;
    }
    const items = visibleGroupItems(entry.group, role);
    if (items.length > 0) {
      out.push({ type: 'group', group: { ...entry.group, items } });
    }
  }
  return out;
}

export const ADMIN_PAGE_TITLES: Record<string, string> = {
  ...Object.fromEntries(
    ADMIN_NAV_STRUCTURE.flatMap((entry) =>
      entry.type === 'item'
        ? [[entry.item.href, entry.item.label]]
        : entry.group.items.map((item) => [item.href, item.label])
    )
  ),
  '/ops': 'Overview',
  '/commands': 'Overview',
  '/overview': 'Inicio',
  '/playground': 'Chat',
  '/sandbox': 'Sandbox',
  '/projects': 'Proyectos',
  '/knowledge': 'Conocimiento',
  '/productividad': 'Productividad',
  '/plataforma': 'Plataforma',
  '/integraciones': 'Integraciones',
  '/administracion': 'Administración',
  '/policies': 'Reglas base',
  '/integrations': 'Integraciones',
  '/gen': 'Gen',
  '/gen/image': 'Imágenes',
  '/telegram': 'Telegram',
  '/integrations/edge-devices': 'Edge devices',
  '/integrations/sensory-node': 'Sensory node',
  '/admin/access': 'Acceso',
  '/admin': 'Administración',
  '/vnc': 'Sandbox',
  '/kanban': 'Tablero',
  '/settings': 'Ajustes',
  '/templates': 'Agentes',
  '/reports': 'Reportes',
};

export function titleForAdminPath(pathname: string): string {
  const entries = Object.entries(ADMIN_PAGE_TITLES).sort((a, b) => b[0].length - a[0].length);
  for (const [prefix, title] of entries) {
    if (pathname === prefix || pathname.startsWith(`${prefix}/`)) return title;
  }
  return 'DuckClaw Admin';
}

export function navItemsForRole(role: AdminRole | undefined): AdminNavItem[] {
  return ADMIN_NAV.filter((item) => itemVisible(item, role));
}
