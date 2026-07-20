import { describe, expect, it } from 'vitest';
import type { McpConnectorPreset, McpConnectorSummary } from '@/services/adminService';
import { resolveMcpConnectorPrimaryAction } from './mcpConnectorPrimaryAction';

function connector(overrides: Partial<McpConnectorSummary> = {}): McpConnectorSummary {
  return {
    connector_id: 'mcp_x',
    tenant_id: 'default',
    display_name: 'X',
    transport: 'streamable_http',
    auth_kind: 'none',
    has_auth: false,
    tool_allowlist: [],
    tool_denylist: [],
    read_only: false,
    egress_hosts: [],
    enabled: true,
    active: true,
    ...overrides,
  };
}

function oauthPreset(): McpConnectorPreset {
  return {
    preset_id: 'notion',
    display_name: 'Notion',
    transport: 'streamable_http',
    auth_kind: 'oauth',
    read_only: true,
    egress_hosts: [],
    tool_allowlist: ['*'],
    tool_denylist: [],
    metadata: { oauth_pkce: true },
  };
}

describe('resolveMcpConnectorPrimaryAction', () => {
  it('prioriza OAuth faltante', () => {
    const action = resolveMcpConnectorPrimaryAction(
      connector({ auth_kind: 'oauth', has_auth: false, preset_id: 'notion' }),
      { preset: oauthPreset(), grantCount: 0, canWrite: true }
    );
    expect(action.kind).toBe('connect_oauth');
  });

  it('prioriza Bearer faltante', () => {
    const action = resolveMcpConnectorPrimaryAction(
      connector({ auth_kind: 'bearer', has_auth: false }),
      { grantCount: 2, canWrite: true }
    );
    expect(action.kind).toBe('configure_bearer');
  });

  it('prioriza grant cuando auth OK y sin grants', () => {
    const action = resolveMcpConnectorPrimaryAction(
      connector({ auth_kind: 'none', has_auth: false }),
      { grantCount: 0, canWrite: true }
    );
    expect(action.kind).toBe('grant');
  });

  it('abre detalle cuando todo OK', () => {
    const action = resolveMcpConnectorPrimaryAction(
      connector({ auth_kind: 'bearer', has_auth: true }),
      { grantCount: 1, canWrite: true, testResult: { ok: true, connector_id: 'mcp_x', transport: '', tool_count: 2, tools: [] } }
    );
    expect(action.kind).toBe('open_detail');
  });

  it('sugiere reconectar tras 401', () => {
    const action = resolveMcpConnectorPrimaryAction(
      connector({ auth_kind: 'oauth', has_auth: true, preset_id: 'notion' }),
      {
        preset: oauthPreset(),
        grantCount: 1,
        canWrite: true,
        testResult: {
          ok: false,
          connector_id: 'mcp_x',
          transport: '',
          tool_count: 0,
          tools: [],
          error: 'HTTP 401',
        },
      }
    );
    expect(action.kind).toBe('connect_oauth');
    expect(action.label).toBe('Reconectar OAuth');
  });

  it('sugiere probar cuando auth lista sin test', () => {
    const action = resolveMcpConnectorPrimaryAction(
      connector({ auth_kind: 'none' }),
      { grantCount: 1, canWrite: true }
    );
    expect(action.label).toBe('Probar');
  });

  it('sin write solo detalle', () => {
    const action = resolveMcpConnectorPrimaryAction(
      connector({ auth_kind: 'bearer', has_auth: false }),
      { grantCount: 0, canWrite: false }
    );
    expect(action.kind).toBe('open_detail');
  });
});
