export type McpTabId = 'connectors' | 'runtime' | 'config' | 'server' | 'tools' | 'catalog';

export const MCP_TABS: { id: McpTabId; label: string; hint: string }[] = [
  {
    id: 'connectors',
    label: 'Conectores',
    hint: 'Registry DB-first, grants por worker',
  },
  {
    id: 'runtime',
    label: 'Runtime',
    hint: 'Proceso HTTP, PM2 y health-check',
  },
  {
    id: 'config',
    label: 'Configuración',
    hint: 'Puerto DB-first y fuente efectiva',
  },
  {
    id: 'server',
    label: 'Servidor',
    hint: 'Comando local y endpoint HTTP',
  },
  {
    id: 'tools',
    label: 'Herramientas',
    hint: 'Tools expuestas por DuckClaw MCP',
  },
  {
    id: 'catalog',
    label: 'Catálogo',
    hint: 'Referencia oficial y stdio',
  },
];

const TAB_IDS = new Set<McpTabId>(MCP_TABS.map((t) => t.id));

export function parseMcpTab(raw: string | null): McpTabId {
  if (raw && TAB_IDS.has(raw as McpTabId)) {
    return raw as McpTabId;
  }
  return 'connectors';
}

export const MCP_LEGACY_TAB_REDIRECTS: Record<string, McpTabId> = {
  '/mcp/connectors': 'connectors',
  '/mcp/runtime': 'runtime',
  '/mcp/config': 'config',
  '/mcp/server': 'server',
  '/mcp/tools': 'tools',
  '/mcp/catalog': 'catalog',
};
