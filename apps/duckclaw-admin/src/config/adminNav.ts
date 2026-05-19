/** Fuente única de rutas del panel admin (Sidebar + Topbar). */

export type NavSection = 'core' | 'integrations' | 'admin' | 'footer';

export type AdminNavItem = {
  href: string;
  label: string;
  section: NavSection;
  /** Solo visible si usuario.rol === 'admin' */
  adminOnly?: boolean;
};

export type AdminNavGroup = {
  id: string;
  label: string;
  items: readonly AdminNavItem[];
};

export type AdminNavEntry =
  | { type: 'item'; item: AdminNavItem }
  | { type: 'group'; group: AdminNavGroup };

export const INTEGRATIONS_NAV_GROUP: AdminNavGroup = {
  id: 'integrations',
  label: 'Integraciones',
  items: [
    { href: '/telegram', label: 'Telegram', section: 'integrations' },
    { href: '/integrations/edge-devices', label: 'Edge devices', section: 'integrations' },
  ],
};

const CORE_AND_ADMIN_NAV: readonly AdminNavItem[] = [
  { href: '/overview', label: 'Overview', section: 'core' },
  { href: '/kanban', label: 'Tablero', section: 'core' },
  { href: '/templates', label: 'Workers', section: 'core' },
  { href: '/projects', label: 'Proyectos', section: 'core' },
  { href: '/mcp', label: 'MCP', section: 'core' },
  { href: '/skills', label: 'Skills', section: 'core' },
  { href: '/playground', label: 'Playground', section: 'core' },
  { href: '/vnc', label: 'VNC', section: 'core', adminOnly: true },
  { href: '/runtime', label: 'Runtime', section: 'core' },
  { href: '/commands', label: 'Fly commands', section: 'core' },
  { href: '/duckdb', label: 'DuckDB', section: 'core' },
  { href: '/train', label: 'Train', section: 'core' },
  { href: '/admin/access', label: 'Acceso', section: 'admin', adminOnly: true },
  { href: '/audit', label: 'Auditoría', section: 'admin', adminOnly: true },
  { href: '/settings', label: 'Ajustes', section: 'footer' },
] as const;

/** Orden del sidebar: ítems planos + grupo Integraciones en el hueco tras Runtime. */
export const ADMIN_NAV_STRUCTURE: readonly AdminNavEntry[] = [
  { type: 'item', item: CORE_AND_ADMIN_NAV[0] },
  { type: 'item', item: CORE_AND_ADMIN_NAV[1] },
  { type: 'item', item: CORE_AND_ADMIN_NAV[2] },
  { type: 'item', item: CORE_AND_ADMIN_NAV[3] },
  { type: 'item', item: CORE_AND_ADMIN_NAV[4] },
  { type: 'item', item: CORE_AND_ADMIN_NAV[5] },
  { type: 'item', item: CORE_AND_ADMIN_NAV[6] },
  { type: 'item', item: CORE_AND_ADMIN_NAV[7] },
  { type: 'group', group: INTEGRATIONS_NAV_GROUP },
  { type: 'item', item: CORE_AND_ADMIN_NAV[8] },
  { type: 'item', item: CORE_AND_ADMIN_NAV[9] },
  { type: 'item', item: CORE_AND_ADMIN_NAV[10] },
  { type: 'item', item: CORE_AND_ADMIN_NAV[11] },
  { type: 'item', item: CORE_AND_ADMIN_NAV[12] },
  { type: 'item', item: CORE_AND_ADMIN_NAV[13] },
  { type: 'item', item: CORE_AND_ADMIN_NAV[14] },
];

/** Lista plana (compat tests / búsquedas). */
export const ADMIN_NAV: readonly AdminNavItem[] = [
  ...CORE_AND_ADMIN_NAV.slice(0, 8),
  ...INTEGRATIONS_NAV_GROUP.items,
  ...CORE_AND_ADMIN_NAV.slice(9),
];

function itemVisible(item: AdminNavItem, isAdmin: boolean): boolean {
  return !item.adminOnly || isAdmin;
}

export function navEntriesForRole(isAdmin: boolean): AdminNavEntry[] {
  return ADMIN_NAV_STRUCTURE.flatMap((entry) => {
    if (entry.type === 'item') {
      return itemVisible(entry.item, isAdmin) ? [entry] : [];
    }
    const items = entry.group.items.filter((i) => itemVisible(i, isAdmin));
    return items.length > 0 ? [{ type: 'group' as const, group: { ...entry.group, items } }] : [];
  });
}

/** Títulos del Topbar; incluye prefijos de rutas anidadas. */
export const ADMIN_PAGE_TITLES: Record<string, string> = {
  ...Object.fromEntries(ADMIN_NAV.map((item) => [item.href, item.label])),
  '/ops': 'Overview',
  '/projects': 'Proyectos',
  '/projects/new': 'Nuevo proyecto',
  '/integrations': 'Integraciones',
  '/admin': 'Administración',
};

export function titleForAdminPath(pathname: string): string {
  const entries = Object.entries(ADMIN_PAGE_TITLES).sort((a, b) => b[0].length - a[0].length);
  for (const [prefix, title] of entries) {
    if (pathname === prefix || pathname.startsWith(`${prefix}/`)) return title;
  }
  return 'DuckClaw Admin';
}

export function navItemsForRole(isAdmin: boolean): AdminNavItem[] {
  return ADMIN_NAV.filter((item) => itemVisible(item, isAdmin));
}
