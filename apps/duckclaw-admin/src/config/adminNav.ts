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
  items: readonly AdminNavItem[];
};

export type AdminNavEntry =
  | { type: 'item'; item: AdminNavItem }
  | { type: 'group'; group: AdminNavGroup };

export const USER_WORKSPACE_NAV_GROUP: AdminNavGroup = {
  id: 'user-workspace',
  label: 'Tu espacio',
  hint: 'Crea, conversa y retoma trabajo',
  items: [
    { href: '/overview', label: 'Inicio', section: 'core', audience: 'user' },
    { href: '/playground', label: 'Chat', section: 'core', audience: 'user' },
    { href: '/templates', label: 'Mis agentes', section: 'core', audience: 'user' },
    { href: '/projects/new', label: 'Crear agente', section: 'core', audience: 'user' },
    { href: '/kanban', label: 'Tablero', section: 'core', audience: 'user' },
    { href: '/settings', label: 'Ajustes', section: 'footer', audience: 'user' },
  ],
};

export const OPERATION_NAV_GROUP: AdminNavGroup = {
  id: 'operation',
  label: 'Operación',
  hint: 'Estado, chat y tablero diario',
  items: [
    { href: '/overview', label: 'Overview', section: 'core', audience: 'admin' },
    { href: '/playground', label: 'Playground', section: 'core', audience: 'admin' },
    { href: '/kanban', label: 'Tablero', section: 'core', audience: 'admin' },
    { href: '/audit', label: 'Auditoría', section: 'admin', audience: 'admin', adminOnly: true },
  ],
};

export const BUILD_NAV_GROUP: AdminNavGroup = {
  id: 'build',
  label: 'Agentes',
  hint: 'Agentes, proyectos y capacidades',
  items: [
    { href: '/templates', label: 'Workers', section: 'core', audience: 'admin' },
    { href: '/projects', label: 'Proyectos', section: 'core', audience: 'admin' },
    { href: '/skills', label: 'Skills', section: 'core', audience: 'admin' },
    { href: '/mcp', label: 'MCP', section: 'core', audience: 'admin' },
    { href: '/gen/image', label: 'Gen Image', section: 'core', audience: 'admin' },
  ],
};

export const DATA_NAV_GROUP: AdminNavGroup = {
  id: 'data',
  label: 'Datos',
  hint: 'Memoria y configuración avanzada',
  items: [
    { href: '/duckdb', label: 'DuckDB', section: 'core', audience: 'admin' },
    { href: '/runtime', label: 'Runtime overrides', section: 'core', audience: 'admin' },
  ],
};

export const INTEGRATIONS_NAV_GROUP: AdminNavGroup = {
  id: 'integrations',
  label: 'Integraciones',
  hint: 'Canales y dispositivos conectados',
  items: [
    { href: '/telegram', label: 'Telegram', section: 'integrations', audience: 'admin' },
    { href: '/integrations/edge-devices', label: 'Edge devices', section: 'integrations', audience: 'admin' },
  ],
};

export const SECURITY_NAV_GROUP: AdminNavGroup = {
  id: 'security',
  label: 'Seguridad',
  hint: 'Usuarios, roles y permisos',
  items: [
    { href: '/admin/access', label: 'Usuarios y roles', section: 'admin', audience: 'admin', adminOnly: true },
  ],
};

export const SYSTEM_NAV_GROUP: AdminNavGroup = {
  id: 'system',
  label: 'Sistema avanzado',
  hint: 'Diagnóstico y operación técnica',
  items: [
    { href: '/settings', label: 'Settings', section: 'footer', audience: 'admin' },
    { href: '/train', label: 'Train', section: 'core', audience: 'admin' },
    { href: '/vnc', label: 'VNC', section: 'core', audience: 'admin', adminOnly: true },
  ],
};

/** Orden del sidebar para usuarios que crean y usan agentes. */
export const USER_NAV_STRUCTURE: readonly AdminNavEntry[] = [
  { type: 'group', group: USER_WORKSPACE_NAV_GROUP },
];

/** Orden del sidebar admin: grupos semánticos para reducir carga cognitiva. */
export const ADMIN_NAV_STRUCTURE: readonly AdminNavEntry[] = [
  { type: 'group', group: OPERATION_NAV_GROUP },
  { type: 'group', group: BUILD_NAV_GROUP },
  { type: 'group', group: DATA_NAV_GROUP },
  { type: 'group', group: INTEGRATIONS_NAV_GROUP },
  { type: 'group', group: SECURITY_NAV_GROUP },
  { type: 'group', group: SYSTEM_NAV_GROUP },
];

/** Lista plana (compat tests / búsquedas). */
export const ADMIN_NAV: readonly AdminNavItem[] = [
  ...USER_WORKSPACE_NAV_GROUP.items,
  ...OPERATION_NAV_GROUP.items,
  ...BUILD_NAV_GROUP.items,
  ...DATA_NAV_GROUP.items,
  ...INTEGRATIONS_NAV_GROUP.items,
  ...SECURITY_NAV_GROUP.items,
  ...SYSTEM_NAV_GROUP.items,
];

function itemVisible(item: AdminNavItem, role: AdminRole | undefined): boolean {
  const isAdmin = isAdminRole(role);
  if (item.adminOnly && !isAdmin) return false;
  if (item.audience === 'admin') return isAdmin;
  if (item.audience === 'user') return !isAdmin;
  return true;
}

export function navEntriesForRole(role: AdminRole | undefined): AdminNavEntry[] {
  const structure = isAdminRole(role) ? ADMIN_NAV_STRUCTURE : USER_NAV_STRUCTURE;
  return structure.flatMap((entry) => {
    if (entry.type === 'item') {
      return itemVisible(entry.item, role) ? [entry] : [];
    }
    const items = entry.group.items.filter((i) => itemVisible(i, role));
    return items.length > 0 ? [{ type: 'group' as const, group: { ...entry.group, items } }] : [];
  });
}

/** Títulos del Topbar; incluye prefijos de rutas anidadas. */
export const ADMIN_PAGE_TITLES: Record<string, string> = {
  ...Object.fromEntries(ADMIN_NAV_STRUCTURE.flatMap((entry) =>
    entry.type === 'item'
      ? [[entry.item.href, entry.item.label]]
      : entry.group.items.map((item) => [item.href, item.label])
  )),
  '/ops': 'Overview',
  '/commands': 'Overview',
  '/projects': 'Proyectos',
  '/projects/new': 'Crear agente',
  '/integrations': 'Integraciones',
  '/gen': 'Gen',
  '/gen/image': 'Image',
  '/admin': 'Administración',
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
