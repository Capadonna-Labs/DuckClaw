/** Pestañas del hub Plataforma — sidebar + contenido en /plataforma?tab= */

export const PLATAFORMA_TABS = [
  { id: 'reglas', label: 'Reglas base', hint: 'Policies de framework y borrador avanzado' },
  { id: 'skills', label: 'Skills', hint: 'Catálogo DuckDB y skills del manifest por agente' },
  { id: 'mcp', label: 'MCP', hint: 'Conectores externos y servidor DuckClaw MCP' },
  { id: 'imagenes', label: 'Imágenes', hint: 'Generación visual ComfyUI' },
  { id: 'duckdb', label: 'DuckDB', hint: 'Explorador de datos' },
  { id: 'runtime', label: 'Runtime', hint: 'Overrides agent_config por bóveda y chat' },
] as const;

export type PlataformaTabId = (typeof PLATAFORMA_TABS)[number]['id'];

const TAB_IDS = new Set<string>(PLATAFORMA_TABS.map((t) => t.id));

export function parsePlataformaTab(raw: string | null): PlataformaTabId {
  if (raw && TAB_IDS.has(raw)) return raw as PlataformaTabId;
  return 'reglas';
}

export function plataformaTabHref(tabId: PlataformaTabId): string {
  return `/plataforma?tab=${tabId}`;
}

export function isPlataformaPath(pathname: string): boolean {
  return pathname === '/plataforma' || pathname.startsWith('/plataforma/');
}
