import type {
  McpConnectorPreset,
  McpConnectorSummary,
  McpConnectorTestResult,
} from '@/services/adminService';
import { mcpConnectorAuthFlags } from '@/lib/mcpConnectorPrimaryAction';
import { trimStr } from '@/lib/utils';

export type McpConnectorStatusFilter = 'all' | 'needs_auth' | 'no_grants' | 'test_failed';

export function isGoogleWorkspacePreset(
  preset?: McpConnectorPreset,
  presetId?: string
): boolean {
  const id = trimStr(presetId || preset?.preset_id);
  return (
    preset?.metadata?.oauth_provider === 'google_workspace' || id.startsWith('google_')
  );
}

export function interpretMcpTestFailure(error: unknown): {
  isAuthFailure: boolean;
  hint: string;
} {
  const msg = trimStr(error).toLowerCase();
  if (
    msg.includes('401') ||
    msg.includes('403') ||
    msg.includes('unauthorized') ||
    msg.includes('invalid token') ||
    msg.includes('expired') ||
    msg.includes('oauth')
  ) {
    return {
      isAuthFailure: true,
      hint: 'Sesión o token inválido — reconecta OAuth o actualiza el Bearer.',
    };
  }
  if (msg.includes('502') || msg.includes('503') || msg.includes('timeout') || msg.includes('timed out')) {
    return { isAuthFailure: false, hint: 'El gateway no alcanzó el servidor MCP. Revisa red/egress.' };
  }
  if (msg.includes('npx') || msg.includes('enoent') || msg.includes('stdio')) {
    return { isAuthFailure: false, hint: 'Fallo stdio local (¿npx/Node en el host del gateway?).' };
  }
  return { isAuthFailure: false, hint: trimStr(error) || 'Test falló — abre Detalle.' };
}

export function mcpConnectorRowHint(params: {
  connector: McpConnectorSummary;
  preset?: McpConnectorPreset;
  grantCount: number;
  testResult?: McpConnectorTestResult;
}): string | null {
  const { connector, preset, grantCount, testResult } = params;
  const { needsAuth, authReady, usesOAuth, usesAdbDevice } = mcpConnectorAuthFlags(connector, preset);

  if (testResult) {
    if (testResult.ok) {
      return `${testResult.tool_count} tools OK · list_tools verificado`;
    }
    return interpretMcpTestFailure(testResult.error || 'Test falló').hint;
  }

  if (needsAuth && !connector.has_auth) {
    if (usesAdbDevice) {
      return 'Conecta ADB y arranca Android-MCP antes de probar o dar grant';
    }
    if (isGoogleWorkspacePreset(preset, connector.preset_id)) {
      return 'Google Workspace — requiere GOOGLE_OAUTH_* en gateway (opcional si no lo usas)';
    }
    return usesOAuth ? 'Conecta OAuth antes de probar o dar grant' : 'Pega el Bearer antes de probar';
  }

  if (authReady && grantCount === 0) {
    return 'Auth lista — falta grant a un worker';
  }

  if (authReady && grantCount > 0) {
    return 'Listo para Playground — prueba list_tools para confirmar';
  }

  return null;
}

export function connectorGrantCount(
  connectorId: string,
  grantsByWorker: Record<string, string[]>
): number {
  let count = 0;
  for (const ids of Object.values(grantsByWorker)) {
    if (ids.includes(connectorId)) count += 1;
  }
  return count;
}

export function filterMcpConnectorsByStatus(
  connectors: readonly McpConnectorSummary[],
  opts: {
    status: McpConnectorStatusFilter;
    grantsByWorker: Record<string, string[]>;
    testResults: Record<string, McpConnectorTestResult>;
    presetById: Record<string, McpConnectorPreset>;
  }
): McpConnectorSummary[] {
  if (opts.status === 'all') return [...connectors];

  return connectors.filter((connector) => {
    const preset = connector.preset_id ? opts.presetById[connector.preset_id] : undefined;
    const { needsAuth } = mcpConnectorAuthFlags(connector, preset);
    const grants = connectorGrantCount(connector.connector_id, opts.grantsByWorker);
    const test = opts.testResults[connector.connector_id];

    if (opts.status === 'needs_auth') {
      return needsAuth && !connector.has_auth;
    }
    if (opts.status === 'no_grants') {
      return grants === 0;
    }
    if (opts.status === 'test_failed') {
      return Boolean(test && !test.ok);
    }
    return true;
  });
}
