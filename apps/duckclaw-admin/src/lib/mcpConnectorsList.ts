import { trimStr } from '@/lib/utils';
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
      trimStr(connector.display_name),
      trimStr(connector.connector_id),
      trimStr(connector.transport),
      trimStr(connector.endpoint_url),
      trimStr(connector.preset_id),
    ]
      .join(' ')
      .toLocaleLowerCase();
    return haystack.includes(needle);
  });
}
