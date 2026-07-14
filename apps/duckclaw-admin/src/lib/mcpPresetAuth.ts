import type { McpConnectorPreset, McpConnectorSummary } from '@/services/adminService';

export function presetAdminLabel(preset: McpConnectorPreset): string {
  const custom = preset.metadata?.admin_label;
  if (typeof custom === 'string' && custom.trim()) return custom.trim();
  return (preset.display_name || preset.preset_id || '').trim() || preset.preset_id;
}

export function presetConnectorId(preset: McpConnectorPreset): string {
  return `mcp_${preset.preset_id}`;
}

export function presetEgressSummary(preset: McpConnectorPreset): string {
  const count = preset.egress_hosts?.length ?? 0;
  if (count === 0) return 'Sin allowlist de hosts';
  if (count === 1) return '1 host remoto en allowlist';
  return `${count} hosts remotos en allowlist`;
}

export function presetUsesOAuthPkce(preset: McpConnectorPreset | undefined): boolean {
  if (!preset?.metadata) return false;
  return preset.metadata.oauth_pkce === true;
}

export function connectorUsesOAuthPkce(
  connector: McpConnectorSummary,
  presetById: Record<string, McpConnectorPreset>
): boolean {
  const presetId = connector.preset_id?.trim();
  if (!presetId) return false;
  return presetUsesOAuthPkce(presetById[presetId]);
}

export function presetTransportLabel(preset: McpConnectorPreset): string {
  const transport = (preset.transport || '').trim().toLowerCase();
  if (transport === 'stdio') return 'Proceso local (stdio)';
  if (transport === 'streamable_http') return 'HTTP remoto (Streamable HTTP)';
  return preset.transport || '—';
}

export function presetAuthKindLabel(preset: McpConnectorPreset): string {
  if (presetUsesOAuthPkce(preset)) return 'OAuth PKCE';
  const kind = (preset.auth_kind || 'none').trim().toLowerCase();
  if (kind === 'bearer') return 'Token Bearer';
  if (kind === 'none') return 'Sin credenciales';
  return kind;
}

/** Presets que requieren connection strings gestionados como secretos de plataforma. */
const SECRET_ENV_PRESETS = new Set([
  'postgres',
  'mysql',
  'cockroachdb',
  'redis',
]);

export function presetAuthHint(preset: McpConnectorPreset): string {
  if (presetUsesOAuthPkce(preset)) {
    return 'Tras crear el conector, usa «Conectar OAuth» en su tarjeta.';
  }
  if (preset.auth_kind === 'bearer') {
    if (preset.preset_id === 'github') {
      return 'Tras crear, pega un GitHub PAT como Bearer (scopes según repos/orgs). Docs: servidor MCP remoto de GitHub.';
    }
    const envVars = preset.metadata?.env_vars as string[] | undefined;
    if (envVars?.length) {
      return `Tras crear, pega el token Bearer. Requiere: ${envVars.join(', ')}.`;
    }
    return 'Tras crear el conector, pega el token Bearer en su tarjeta.';
  }
  if (preset.preset_id && SECRET_ENV_PRESETS.has(preset.preset_id)) {
    const vars = preset.metadata?.secret_env as string[] | undefined;
    const list = vars?.join(', ') ?? 'connection strings';
    return `Configura los secretos de plataforma requeridos: ${list}.`;
  }
  return 'No requiere credenciales adicionales.';
}
