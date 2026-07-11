/** Pestañas del hub Plataforma — sidebar + contenido en /plataforma?tab= */

export const PLATAFORMA_TABS = [
  { id: 'reglas', label: 'Reglas base', hint: 'Policies de framework y wizard' },
  { id: 'skills', label: 'Skills', hint: 'Capacidades del framework (manifest) — distinto de tools MCP externas' },
  { id: 'mcp', label: 'MCP', hint: 'Conectores externos, servidor DuckClaw y catálogo' },
  { id: 'imagenes', label: 'Imágenes', hint: 'Generación visual ComfyUI' },
  { id: 'duckdb', label: 'DuckDB', hint: 'Explorador de datos y grafos' },
  { id: 'runtime', label: 'Runtime', hint: 'Ajustes agent_config por vault' },
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
