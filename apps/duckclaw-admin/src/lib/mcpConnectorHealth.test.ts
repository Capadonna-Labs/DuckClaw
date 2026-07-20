import { describe, expect, it } from 'vitest';
import type { McpConnectorPreset, McpConnectorSummary } from '@/services/adminService';
import {
  filterMcpConnectorsByStatus,
  interpretMcpTestFailure,
  mcpConnectorRowHint,
} from './mcpConnectorHealth';

function connector(overrides: Partial<McpConnectorSummary> = {}): McpConnectorSummary {
  return {
    connector_id: 'mcp_x',
    tenant_id: 'default',
    display_name: 'X',
    transport: 'streamable_http',
    auth_kind: 'bearer',
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

describe('interpretMcpTestFailure', () => {
  it('detects auth failures', () => {
    const out = interpretMcpTestFailure('HTTP 401 Unauthorized');
    expect(out.isAuthFailure).toBe(true);
  });
});

describe('mcpConnectorRowHint', () => {
  it('shows tool count on success', () => {
    expect(
      mcpConnectorRowHint({
        connector: connector({ has_auth: true }),
        grantCount: 1,
        testResult: {
          ok: true,
          connector_id: 'mcp_x',
          transport: 'http',
          tool_count: 3,
          tools: [],
        },
      })
    ).toContain('3 tools');
  });

  it('nudges grant when auth ready', () => {
    expect(
      mcpConnectorRowHint({
        connector: connector({ auth_kind: 'none', has_auth: false }),
        grantCount: 0,
      })
    ).toContain('grant');
  });
});

describe('filterMcpConnectorsByStatus', () => {
  const rows = [
    connector({ connector_id: 'a', has_auth: false }),
    connector({ connector_id: 'b', has_auth: true }),
  ];

  it('filters missing auth', () => {
    const out = filterMcpConnectorsByStatus(rows, {
      status: 'needs_auth',
      grantsByWorker: {},
      testResults: {},
      presetById: {},
    });
    expect(out.map((r) => r.connector_id)).toEqual(['a']);
  });

  it('filters test failed', () => {
    const out = filterMcpConnectorsByStatus(rows, {
      status: 'test_failed',
      grantsByWorker: {},
      testResults: {
        b: {
          ok: false,
          connector_id: 'b',
          transport: '',
          tool_count: 0,
          tools: [],
          error: 'fail',
        },
      },
      presetById: {},
    });
    expect(out.map((r) => r.connector_id)).toEqual(['b']);
  });
});
