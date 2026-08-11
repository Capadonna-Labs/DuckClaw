import type {
  McpConnectorPreset,
  McpConnectorSummary,
  McpConnectorTestResult,
} from '@/services/adminService';
import { presetUsesAdbDevice, presetUsesOAuthPkce } from '@/lib/mcpPresetAuth';
import { interpretMcpTestFailure } from '@/lib/mcpConnectorHealth';
import { trimStr } from '@/lib/utils';

export type McpConnectorPrimaryKind =
  | 'connect_oauth'
  | 'connect_adb'
  | 'configure_bearer'
  | 'grant'
  | 'open_detail';

export type McpConnectorPrimaryAction = {
  kind: McpConnectorPrimaryKind;
  label: string;
};

export function mcpConnectorAuthFlags(
  connector: McpConnectorSummary,
  preset?: McpConnectorPreset
): {
  usesOAuth: boolean;
  usesAdbDevice: boolean;
  needsBearer: boolean;
  needsAuth: boolean;
  authReady: boolean;
} {
  const usesOAuth = presetUsesOAuthPkce(preset);
  const usesAdbDevice =
    presetUsesAdbDevice(preset) || trimStr(connector.auth_kind).toLowerCase() === 'adb';
  const needsBearer = connector.auth_kind === 'bearer' && !usesOAuth;
  const needsAuth = needsBearer || usesOAuth || usesAdbDevice;
  const authReady = !needsAuth || connector.has_auth;
  return { usesOAuth, usesAdbDevice, needsBearer, needsAuth, authReady };
}

/**
 * CTA primaria de la fila (inventario). OAuth/ADB se disparan inline;
 * Bearer/grant/detalle abren o enfocan el drawer.
 */
export function resolveMcpConnectorPrimaryAction(
  connector: McpConnectorSummary,
  opts: {
    preset?: McpConnectorPreset;
    grantCount: number;
    canWrite: boolean;
    testResult?: McpConnectorTestResult;
  }
): McpConnectorPrimaryAction {
  const { usesOAuth, usesAdbDevice, needsBearer, authReady } = mcpConnectorAuthFlags(
    connector,
    opts.preset
  );

  const authTestFailed =
    opts.testResult &&
    !opts.testResult.ok &&
    interpretMcpTestFailure(opts.testResult.error || '').isAuthFailure;

  if (opts.canWrite && usesOAuth && (!connector.has_auth || authTestFailed)) {
    return {
      kind: 'connect_oauth',
      label: connector.has_auth || authTestFailed ? 'Reconectar OAuth' : 'Conectar OAuth',
    };
  }
  if (opts.canWrite && usesAdbDevice && (!connector.has_auth || authTestFailed)) {
    return {
      kind: 'connect_adb',
      label: connector.has_auth ? 'Refrescar ADB' : 'Conectar ADB',
    };
  }
  if (opts.canWrite && needsBearer && (!connector.has_auth || authTestFailed)) {
    return {
      kind: 'configure_bearer',
      label: connector.has_auth ? 'Actualizar token' : 'Configurar token',
    };
  }
  if (opts.canWrite && authReady && opts.grantCount === 0) {
    return { kind: 'grant', label: 'Dar grant' };
  }
  if (opts.canWrite && authReady && !opts.testResult) {
    return { kind: 'open_detail', label: 'Probar' };
  }
  return { kind: 'open_detail', label: 'Detalle' };
}
