import type { McpConnectorSummary } from '@/services/adminService';

export const MCP_CONNECTORS_PAGE_SIZE = 10;

/** Evita tratar autofill de login como filtro MCP (ponytail: heurística @). */
export function looksLikeAutofillEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}

/** Filtra conectores MCP en memoria (sin llamadas API). */
export function filterMcpConnectors(
  connectors: readonly McpConnectorSummary[],
  query: string
): McpConnectorSummary[] {
  const needle = query.trim().toLocaleLowerCase();
  if (!needle) return [...connectors];
  return connectors.filter((connector) => {
    const haystack = [
      connector.display_name,
      connector.connector_id,
      connector.transport,
      connector.endpoint_url ?? '',
      connector.preset_id ?? '',
    ]
      .join(' ')
      .toLocaleLowerCase();
    return haystack.includes(needle);
  });
}
