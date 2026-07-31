import { adminFetch } from './http';

export interface McpConnectorSummary {
  connector_id: string;
  tenant_id: string;
  display_name: string;
  transport: string;
  endpoint_url?: string;
  launch_command?: string;
  launch_args?: string[];
  auth_kind: string;
  has_auth: boolean;
  tool_allowlist: string[];
  tool_denylist: string[];
  read_only: boolean;
  egress_hosts: string[];
  preset_id?: string;
  enabled: boolean;
  active: boolean;
  metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export interface McpConnectorPreset {
  preset_id: string;
  display_name: string;
  transport: string;
  endpoint_url?: string;
  launch_command?: string;
  launch_args?: string[];
  auth_kind: string;
  read_only: boolean;
  egress_hosts: string[];
  tool_allowlist: string[];
  tool_denylist: string[];
  metadata?: Record<string, unknown>;
}

export interface McpConnectorTestResult {
  ok: boolean;
  connector_id: string;
  transport: string;
  tool_count: number;
  tools: { name: string; description?: string }[];
  error?: string;
}

export interface McpToolInfo {
  name: string;
  description: string;
  server: string;
}

export const mcpApi = {
  getMcpLiveStatus: () =>
    adminFetch<{
      reachable: boolean;
      port: string;
      url: string;
      command: string;
      status_code?: number;
      service?: string;
      hint?: string;
      error?: string;
    }>('/mcp-status'),
  listMcpConnectors: () =>
    adminFetch<{ connectors: McpConnectorSummary[] }>('/mcp/connectors').then((r) => r.connectors),
  listMcpConnectorPresets: () =>
    adminFetch<{ presets: McpConnectorPreset[] }>('/mcp/connectors/presets').then((r) => r.presets),
  createMcpConnector: (body: { preset_id: string; connector_id?: string; display_name?: string }) =>
    adminFetch<{ ok: boolean; task_id: string; connector: McpConnectorSummary | null }>(
      '/mcp/connectors',
      {
        method: 'POST',
        body: JSON.stringify(body),
      }
    ),
  setMcpConnectorAuth: (connectorId: string, bearerToken: string) =>
    adminFetch<{ ok: boolean; task_id: string }>(`/mcp/connectors/${encodeURIComponent(connectorId)}/auth`, {
      method: 'POST',
      body: JSON.stringify({ bearer_token: bearerToken }),
    }),
  startMcpConnectorOAuth: (connectorId: string, redirectUri?: string) =>
    adminFetch<{ ok: boolean; authorization_url: string; state: string; redirect_uri: string }>(
      `/mcp/connectors/${encodeURIComponent(connectorId)}/oauth/start`,
      {
        method: 'POST',
        body: JSON.stringify({ redirect_uri: redirectUri || '' }),
      }
    ),
  testMcpConnector: (connectorId: string) =>
    adminFetch<McpConnectorTestResult>(`/mcp/connectors/${encodeURIComponent(connectorId)}/test`, {
      method: 'POST',
    }),
  grantMcpConnector: (connectorId: string, workerId: string) =>
    adminFetch<{ ok: boolean; task_id: string; worker_id: string; worker_uid: string }>(
      `/mcp/connectors/${encodeURIComponent(connectorId)}/grants`,
      {
        method: 'POST',
        body: JSON.stringify({ worker_id: workerId }),
      }
    ),
  revokeMcpConnectorGrant: (connectorId: string, workerId: string) =>
    adminFetch<{ ok: boolean; task_id: string }>(
      `/mcp/connectors/${encodeURIComponent(connectorId)}/grants/${encodeURIComponent(workerId)}`,
      { method: 'DELETE' }
    ),
  deactivateMcpConnector: (connectorId: string) =>
    adminFetch<{ ok: boolean; task_id: string }>(`/mcp/connectors/${encodeURIComponent(connectorId)}`, {
      method: 'DELETE',
    }),
  getMcpCatalog: () =>
    adminFetch<{
      duckclaw_mcp: {
        command: string;
        url: string;
        port?: string;
        source?: string;
        runtime_key?: string;
        tools: McpToolInfo[];
        live?: { reachable: boolean; status_code?: number; error?: string; port?: string; url?: string };
      };
      stdio_servers: { id: string; enabled: boolean; note: string }[];
      official_reference: {
        source_repo: string;
        source_label: string;
        registry_url: string;
        servers: {
          id: string;
          name: string;
          description: string;
          runtime: string;
          install: string;
          repo_path: string;
        }[];
      };
      github_note: string;
      youtube_transcript_note?: string;
      _gateway_stale?: boolean;
    }>('/catalog/mcp'),
};
