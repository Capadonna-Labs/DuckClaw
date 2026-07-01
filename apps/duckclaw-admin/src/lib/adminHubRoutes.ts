/** Rutas hijas que activan cada hub en el sidebar «Más». */

export const PRODUCTIVIDAD_HUB_PATHS = ['/productividad', '/reports', '/kanban'] as const;

export const PLATAFORMA_HUB_PATHS = [
  '/plataforma',
  '/policies',
  '/skills',
  '/mcp',
  '/gen/image',
  '/duckdb',
  '/runtime',
] as const;

export const INTEGRACIONES_HUB_PATHS = [
  '/integraciones',
  '/integrations',
  '/telegram',
] as const;

export const ADMINISTRACION_HUB_PATHS = [
  '/administracion',
  '/admin/access',
  '/audit',
  '/settings',
] as const;

export function pathnameMatchesHub(pathname: string, hubHref: string): boolean {
  if (hubHref === '/productividad') {
    return PRODUCTIVIDAD_HUB_PATHS.some(
      (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
    );
  }
  if (hubHref === '/plataforma') {
    return PLATAFORMA_HUB_PATHS.some(
      (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
    );
  }
  if (hubHref === '/integraciones') {
    return INTEGRACIONES_HUB_PATHS.some(
      (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
    );
  }
  if (hubHref === '/administracion') {
    return ADMINISTRACION_HUB_PATHS.some(
      (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`)
    );
  }
  return pathname === hubHref || pathname.startsWith(`${hubHref}/`);
}
