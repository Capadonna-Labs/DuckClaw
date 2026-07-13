import { describe, expect, it } from 'vitest';
import type { McpConnectorSummary } from '@/services/adminService';
import { filterMcpConnectors, MCP_CONNECTORS_PAGE_SIZE } from './mcpConnectorsList';
import { paginateItems } from './pagination';

function sample(id: string, name: string, extra: Partial<McpConnectorSummary> = {}): McpConnectorSummary {
  return {
    connector_id: id,
    tenant_id: 'default',
    display_name: name,
    transport: 'streamable_http',
    auth_kind: 'bearer',
    has_auth: false,
    tool_allowlist: [],
    tool_denylist: [],
    read_only: false,
    egress_hosts: [],
    enabled: true,
    active: true,
    ...extra,
  };
}

const fixtures = [
  sample('higgsfield', 'Higgsfield (imagen/video)', {
    endpoint_url: 'https://mcp.higgsfield.ai/mcp',
    preset_id: 'remote_http_oauth',
  }),
  sample('mcp_fetch', 'Fetch', { transport: 'stdio', preset_id: 'mcp_fetch' }),
  sample('github_mcp', 'GitHub MCP', { endpoint_url: 'https://api.github.com' }),
];

describe('filterMcpConnectors', () => {
  it('returns all rows when query is empty', () => {
    expect(filterMcpConnectors(fixtures, '')).toHaveLength(3);
  });

  it('matches display_name, id, transport, endpoint and preset', () => {
    expect(filterMcpConnectors(fixtures, 'higgsfield')).toHaveLength(1);
    expect(filterMcpConnectors(fixtures, 'FETCH')[0]?.connector_id).toBe('mcp_fetch');
    expect(filterMcpConnectors(fixtures, 'remote_http_oauth')).toHaveLength(1);
    expect(filterMcpConnectors(fixtures, 'no-match')).toEqual([]);
  });
});

describe('mcp connectors pagination', () => {
  it('pages 10 items and clamps page', () => {
    const many = Array.from({ length: 23 }, (_, index) =>
      sample(`connector_${index}`, `Connector ${index}`)
    );
    const page1 = paginateItems(filterMcpConnectors(many, ''), 1, MCP_CONNECTORS_PAGE_SIZE);
    const page3 = paginateItems(filterMcpConnectors(many, ''), 3, MCP_CONNECTORS_PAGE_SIZE);
    expect(page1.items).toHaveLength(10);
    expect(page1.totalPages).toBe(3);
    expect(page3.items).toHaveLength(3);
    expect(page3.currentPage).toBe(3);

    const filteredMany = filterMcpConnectors(many, 'connector_1');
    expect(filteredMany).toHaveLength(11);
    const clamped = paginateItems(filteredMany, 99, MCP_CONNECTORS_PAGE_SIZE);
    expect(clamped.currentPage).toBe(2);
    expect(clamped.items).toHaveLength(1);
  });
});
