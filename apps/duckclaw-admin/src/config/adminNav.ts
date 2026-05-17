/** Fuente única de rutas del panel admin (Sidebar + Topbar). */

export type NavSection = 'core' | 'admin' | 'footer';

export type AdminNavItem = {
  href: string;
  label: string;
  section: NavSection;
  /** Solo visible si usuario.rol === 'admin' */
  adminOnly?: boolean;
};

export const ADMIN_NAV: readonly AdminNavItem[] = [
  { href: '/overview', label: 'Overview', section: 'core' },
  { href: '/kanban', label: 'Tablero', section: 'core' },
  { href: '/templates', label: 'Plantillas', section: 'core' },
  { href: '/skills', label: 'Skills', section: 'core' },
  { href: '/mcp', label: 'MCP', section: 'core' },
  { href: '/projects/new', label: 'Nuevo proyecto', section: 'core' },
  { href: '/playground', label: 'Playground', section: 'core' },
  { href: '/runtime', label: 'Runtime', section: 'core' },
  { href: '/telegram', label: 'Telegram', section: 'core' },
  { href: '/commands', label: 'Fly commands', section: 'core' },
  { href: '/duckdb', label: 'DuckDB', section: 'core' },
  { href: '/traces', label: 'Traces', section: 'core' },
  { href: '/ops', label: 'Operaciones', section: 'admin', adminOnly: true },
  { href: '/audit', label: 'Auditoría', section: 'admin', adminOnly: true },
  { href: '/settings', label: 'Ajustes', section: 'footer' },
] as const;

/** Títulos del Topbar; incluye prefijos de rutas anidadas. */
export const ADMIN_PAGE_TITLES: Record<string, string> = {
  ...Object.fromEntries(ADMIN_NAV.map((item) => [item.href, item.label])),
  '/projects': 'Proyectos',
};

export function titleForAdminPath(pathname: string): string {
  for (const [prefix, title] of Object.entries(ADMIN_PAGE_TITLES)) {
    if (pathname === prefix || pathname.startsWith(`${prefix}/`)) return title;
  }
  return 'DuckClaw Admin';
}

export function navItemsForRole(isAdmin: boolean): AdminNavItem[] {
  return ADMIN_NAV.filter((item) => !item.adminOnly || isAdmin);
}
