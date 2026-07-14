export type McpTabId = 'connectors' | 'config' | 'catalog';

export const MCP_TABS: { id: McpTabId; label: string; hint: string }[] = [
  {
    id: 'connectors',
    label: 'Conectores',
    hint: 'Plantillas empaquetadas → instancia en DuckDB (OAuth, pruebas, grants por worker)',
  },
  {
    id: 'config',
    label: 'Servidor',
    hint: 'Proceso DuckClaw MCP (PM2), puerto y salud HTTP',
  },
  {
    id: 'catalog',
    label: 'Referencia',
    hint: 'Registro oficial MCP y stdio locales (documentación; no crea conectores)',
  },
];

const TAB_IDS = new Set<McpTabId>(MCP_TABS.map((t) => t.id));

/** Tabs retirados — redirigen a la sección unificada. */
const LEGACY_TAB_ALIASES: Record<string, McpTabId> = {
  runtime: 'config',
  server: 'config',
  tools: 'config',
};

export function parseMcpTab(raw: string | null): McpTabId {
  if (raw) {
    const legacy = LEGACY_TAB_ALIASES[raw];
    if (legacy) return legacy;
    if (TAB_IDS.has(raw as McpTabId)) return raw as McpTabId;
  }
  return 'connectors';
}

export const MCP_LEGACY_TAB_REDIRECTS: Record<string, McpTabId> = {
  '/mcp/connectors': 'connectors',
  '/mcp/runtime': 'config',
  '/mcp/config': 'config',
  '/mcp/server': 'config',
  '/mcp/tools': 'config',
  '/mcp/catalog': 'catalog',
};
