export type McpTabId = 'connectors' | 'config' | 'catalog';

export const MCP_TABS: { id: McpTabId; label: string; hint: string }[] = [
  {
    id: 'connectors',
    label: 'Conectores',
    hint: 'OAuth, pruebas y grants por worker sobre conectores ya creados',
  },
  {
    id: 'config',
    label: 'Configuración',
    hint: 'Alta de conectores, runtime PM2, puerto y endpoint HTTP',
  },
  {
    id: 'catalog',
    label: 'Catálogo',
    hint: 'Referencia oficial MCP y stdio empaquetados',
  },
];

const TAB_IDS = new Set<McpTabId>(MCP_TABS.map((t) => t.id));

/** Tabs retirados — redirigen a Configuración unificada. */
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
