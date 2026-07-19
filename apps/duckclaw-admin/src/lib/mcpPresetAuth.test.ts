import { describe, expect, it } from 'vitest';
import type { McpConnectorPreset } from '@/services/adminService';
import {
  existingPresetIdsFromConnectors,
  groupMcpPresetsForSelect,
  presetAdminLabel,
  presetSelectGroupId,
} from '@/lib/mcpPresetAuth';

function preset(partial: Partial<McpConnectorPreset> & { preset_id: string }): McpConnectorPreset {
  return {
    display_name: partial.display_name || partial.preset_id,
    transport: partial.transport || 'stdio',
    auth_kind: partial.auth_kind || 'none',
    endpoint_url: partial.endpoint_url,
    egress_hosts: partial.egress_hosts || [],
    metadata: partial.metadata || {},
    ...partial,
  } as McpConnectorPreset;
}

describe('mcpPresetAuth selector helpers', () => {
  it('uses display_name as product label, not transport admin_label', () => {
    const row = preset({
      preset_id: 'google_gmail',
      display_name: 'Google Gmail',
      metadata: { admin_label: 'HTTP remoto · OAuth PKCE (Gmail)', oauth_pkce: true },
    });
    expect(presetAdminLabel(row)).toBe('Google Gmail');
  });

  it('groups remote oauth, bearer, databases and local stdio', () => {
    const rows = [
      preset({
        preset_id: 'notion',
        display_name: 'Notion',
        transport: 'streamable_http',
        auth_kind: 'bearer',
        metadata: { oauth_pkce: true },
      }),
      preset({
        preset_id: 'github',
        display_name: 'GitHub',
        transport: 'streamable_http',
        auth_kind: 'bearer',
      }),
      preset({
        preset_id: 'postgres',
        display_name: 'PostgreSQL',
        transport: 'stdio',
        metadata: { secret_env: ['POSTGRES_URL'] },
      }),
      preset({
        preset_id: 'fetch',
        display_name: 'MCP Fetch',
        transport: 'stdio',
      }),
    ];
    expect(presetSelectGroupId(rows[0])).toBe('remote_oauth');
    expect(presetSelectGroupId(rows[1])).toBe('remote_bearer');
    expect(presetSelectGroupId(rows[2])).toBe('databases');
    expect(presetSelectGroupId(rows[3])).toBe('local_stdio');

    const groups = groupMcpPresetsForSelect(rows);
    expect(groups.map((g) => g.id)).toEqual([
      'remote_oauth',
      'remote_bearer',
      'databases',
      'local_stdio',
    ]);
    expect(groups[0].presets[0].preset_id).toBe('notion');
  });

  it('detects already materialized presets', () => {
    const ids = existingPresetIdsFromConnectors([
      { preset_id: 'notion', connector_id: 'mcp_notion' },
      { preset_id: '', connector_id: 'mcp_github' },
    ]);
    expect(ids.has('notion')).toBe(true);
    expect(ids.has('github')).toBe(true);
  });

  it('filters catalog by product name and auth without breaking groups', async () => {
    const { filterMcpPresets, groupFilteredMcpPresetsForSelect } = await import(
      '@/lib/mcpPresetAuth'
    );
    const rows = [
      preset({
        preset_id: 'notion',
        display_name: 'Notion',
        transport: 'streamable_http',
        auth_kind: 'bearer',
        metadata: { oauth_pkce: true },
      }),
      preset({
        preset_id: 'github',
        display_name: 'GitHub',
        transport: 'streamable_http',
        auth_kind: 'bearer',
      }),
      preset({
        preset_id: 'fetch',
        display_name: 'MCP Fetch',
        transport: 'stdio',
      }),
    ];
    expect(filterMcpPresets(rows, 'gmail')).toHaveLength(0);
    expect(filterMcpPresets(rows, 'git').map((p) => p.preset_id)).toEqual(['github']);
    expect(filterMcpPresets(rows, 'oauth').map((p) => p.preset_id)).toEqual(['notion']);
    const grouped = groupFilteredMcpPresetsForSelect(rows, 'http');
    expect(grouped.every((g) => g.presets.length > 0)).toBe(true);
    expect(grouped.flatMap((g) => g.presets).map((p) => p.preset_id).sort()).toEqual([
      'github',
      'notion',
    ]);
  });
});
