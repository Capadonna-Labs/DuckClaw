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

/** Usuario no-admin: flujo mínimo crear → chatear → sandbox. */
export const USER_WORKSPACE_NAV_GROUP: AdminNavGroup = {
  id: 'user-workspace',
  label: 'Tu espacio',
  hint: 'Crea, conversa y retoma trabajo',
  items: [
    { href: '/overview', label: 'Resumen', section: 'core', audience: 'user' },
    { href: '/playground', label: 'Chat', section: 'core', audience: 'user' },
    { href: '/sandbox', label: 'Sandbox', section: 'core', audience: 'user' },
    { href: '/templates', label: 'Mis agentes', section: 'core', audience: 'user' },
    { href: '/projects', label: 'Proyectos', section: 'core', audience: 'user' },
    { href: '/settings', label: 'Ajustes', section: 'footer', audience: 'user' },
  ],
};

/** Admin — 3 grupos en lugar de 7 (Trabajo · Estudio · Plataforma). */
export const WORK_NAV_GROUP: AdminNavGroup = {
  id: 'work',
  label: 'Trabajo',
  hint: 'Operación diaria',
  items: [
    { href: '/overview', label: 'Resumen', section: 'core', audience: 'admin' },
    { href: '/playground', label: 'Chat', section: 'core', audience: 'admin' },
    { href: '/sandbox', label: 'Sandbox', section: 'core', audience: 'admin' },
    { href: '/kanban', label: 'Tablero', section: 'core', audience: 'admin' },
  ],
};

export const STUDIO_NAV_GROUP: AdminNavGroup = {
  id: 'studio',
  label: 'Estudio',
  hint: 'Agentes, conocimiento e informes',
  items: [
    { href: '/projects', label: 'Proyectos', section: 'core', audience: 'admin' },
    { href: '/templates', label: 'Agentes', section: 'core', audience: 'admin' },
    { href: '/knowledge', label: 'Conocimiento', section: 'core', audience: 'admin' },
    { href: '/reports', label: 'Reportes', section: 'core', audience: 'admin' },
  ],
};

export const PLATFORM_NAV_GROUP: AdminNavGroup = {
  id: 'platform',
  label: 'Plataforma',
  hint: 'Runtime, integraciones y seguridad',
  items: [
    { href: '/skills', label: 'Skills', section: 'core', audience: 'admin' },
    { href: '/mcp', label: 'MCP', section: 'core', audience: 'admin' },
    { href: '/gen/image', label: 'Imágenes', section: 'core', audience: 'admin' },
    { href: '/duckdb', label: 'DuckDB', section: 'core', audience: 'admin' },
    { href: '/runtime', label: 'Runtime', section: 'core', audience: 'admin' },
    { href: '/policies', label: 'Instrucciones', section: 'core', audience: 'admin' },
    { href: '/integrations/edge-devices', label: 'Edge devices', section: 'integrations', audience: 'admin' },
    { href: '/integrations/sensory-node', label: 'Sensory node', section: 'integrations', audience: 'admin' },
    { href: '/telegram', label: 'Telegram', section: 'integrations', audience: 'admin', adminOnly: true },
    { href: '/admin/access', label: 'Acceso', section: 'admin', audience: 'admin', adminOnly: true },
    { href: '/audit', label: 'Auditoría', section: 'admin', audience: 'admin', adminOnly: true },
    { href: '/settings', label: 'Ajustes', section: 'footer', audience: 'admin' },
  ],
};

/** @deprecated aliases — tests y imports legacy */
export const CONVERSAR_NAV_GROUP = WORK_NAV_GROUP;
export const BUILD_NAV_GROUP = STUDIO_NAV_GROUP;
export const DATA_NAV_GROUP = STUDIO_NAV_GROUP;
export const OPERATION_NAV_GROUP = WORK_NAV_GROUP;
export const PLAYGROUND_NAV_GROUP = WORK_NAV_GROUP;
export const INTEGRATIONS_NAV_GROUP = PLATFORM_NAV_GROUP;
export const SECURITY_NAV_GROUP = PLATFORM_NAV_GROUP;
export const SYSTEM_NAV_GROUP = PLATFORM_NAV_GROUP;

export const USER_NAV_STRUCTURE: readonly AdminNavEntry[] = [
  { type: 'group', group: USER_WORKSPACE_NAV_GROUP },
];

export const ADMIN_NAV_STRUCTURE: readonly AdminNavEntry[] = [
  { type: 'group', group: WORK_NAV_GROUP },
  { type: 'group', group: STUDIO_NAV_GROUP },
  { type: 'group', group: PLATFORM_NAV_GROUP },
];

export const ADMIN_NAV: readonly AdminNavItem[] = [
  ...USER_WORKSPACE_NAV_GROUP.items,
  ...WORK_NAV_GROUP.items,
  ...STUDIO_NAV_GROUP.items,
  ...PLATFORM_NAV_GROUP.items,
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
  const out: AdminNavEntry[] = [];
  for (const entry of structure) {
    if (entry.type === 'item') {
      if (itemVisible(entry.item, role)) out.push(entry);
      continue;
    }
    const items = entry.group.items.filter((i) => itemVisible(i, role));
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
  '/overview': 'Resumen',
  '/playground': 'Playground',
  '/sandbox': 'Sandbox',
  '/projects': 'Proyectos',
  '/knowledge': 'Conocimiento',
  '/policies': 'Instrucciones',
  '/integrations': 'Integraciones',
  '/gen': 'Gen',
  '/gen/image': 'Image',
  '/telegram': 'Telegram',
  '/integrations/edge-devices': 'Edge devices',
  '/integrations/sensory-node': 'Sensory node',
  '/admin/access': 'Acceso',
  '/admin': 'Administración',
  '/vnc': 'Sandbox',
  '/kanban': 'Tablero',
  '/settings': 'Ajustes',
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
