import type { McpConnectorPreset, McpConnectorSummary } from '@/services/adminService';

/** Nombre de producto para UI. Nunca meter transporte/auth en el título. */
export function presetAdminLabel(preset: McpConnectorPreset): string {
  const name = (preset.display_name || preset.preset_id || '').trim();
  return name || preset.preset_id;
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

const DATABASE_PRESET_IDS = new Set([
  'postgres',
  'mysql',
  'cockroachdb',
  'redis',
  'neon',
  'supabase',
  'mongodb',
  'snowflake',
  'sqlite',
  'duckdb',
  'aurora',
  'aws_aurora',
  'pgedge',
  'pg_edge_postgres',
  'dbutils',
  'google_mcp_toolbox',
  'google_db_toolbox',
]);

export type McpPresetSelectGroupId =
  | 'remote_oauth'
  | 'remote_bearer'
  | 'local_stdio'
  | 'databases';

export type McpPresetSelectGroup = {
  id: McpPresetSelectGroupId;
  label: string;
  presets: McpConnectorPreset[];
};

const GROUP_ORDER: McpPresetSelectGroupId[] = [
  'remote_oauth',
  'remote_bearer',
  'databases',
  'local_stdio',
];

const GROUP_LABELS: Record<McpPresetSelectGroupId, string> = {
  remote_oauth: 'Remotos · OAuth',
  remote_bearer: 'Remotos · Token Bearer',
  databases: 'Bases de datos',
  local_stdio: 'Locales · stdio',
};

function isDatabasePreset(preset: McpConnectorPreset): boolean {
  const id = (preset.preset_id || '').trim().toLowerCase();
  if (DATABASE_PRESET_IDS.has(id)) return true;
  if (SECRET_ENV_PRESETS.has(id)) return true;
  if (preset.metadata?.secret_env) return true;
  const name = `${id} ${preset.display_name || ''}`.toLowerCase();
  return /(postgres|mysql|mongo|redis|snowflake|sqlite|duckdb|cockroach|neon|supabase|aurora)/.test(
    name
  );
}

export function presetSelectGroupId(preset: McpConnectorPreset): McpPresetSelectGroupId {
  if (isDatabasePreset(preset)) return 'databases';
  const transport = (preset.transport || '').trim().toLowerCase();
  if (transport === 'streamable_http' || transport === 'http') {
    return presetUsesOAuthPkce(preset) ? 'remote_oauth' : 'remote_bearer';
  }
  return 'local_stdio';
}

/** Agrupa presets para selector; dentro de cada grupo, A→Z por nombre de producto. */
export function groupMcpPresetsForSelect(presets: McpConnectorPreset[]): McpPresetSelectGroup[] {
  const buckets: Record<McpPresetSelectGroupId, McpConnectorPreset[]> = {
    remote_oauth: [],
    remote_bearer: [],
    databases: [],
    local_stdio: [],
  };
  for (const preset of presets) {
    buckets[presetSelectGroupId(preset)].push(preset);
  }
  for (const id of GROUP_ORDER) {
    buckets[id].sort((a, b) =>
      presetAdminLabel(a).localeCompare(presetAdminLabel(b), 'es', { sensitivity: 'base' })
    );
  }
  return GROUP_ORDER.filter((id) => buckets[id].length > 0).map((id) => ({
    id,
    label: GROUP_LABELS[id],
    presets: buckets[id],
  }));
}

/** Filtro de catálogo: nombre, id, auth, transporte y hosts. */
export function filterMcpPresets(
  presets: McpConnectorPreset[],
  query: string
): McpConnectorPreset[] {
  const q = query.trim().toLowerCase();
  if (!q) return presets;
  return presets.filter((preset) => {
    const haystack = [
      preset.preset_id,
      preset.display_name,
      preset.transport,
      preset.auth_kind,
      preset.endpoint_url,
      presetAuthKindLabel(preset),
      presetTransportLabel(preset),
      ...(preset.egress_hosts || []),
    ]
      .filter(Boolean)
      .join(' ')
      .toLowerCase();
    return haystack.includes(q);
  });
}

export function groupFilteredMcpPresetsForSelect(
  presets: McpConnectorPreset[],
  query: string
): McpPresetSelectGroup[] {
  return groupMcpPresetsForSelect(filterMcpPresets(presets, query));
}

export function existingPresetIdsFromConnectors(
  connectors: Pick<McpConnectorSummary, 'preset_id' | 'connector_id'>[]
): Set<string> {
  const ids = new Set<string>();
  for (const connector of connectors) {
    const presetId = (connector.preset_id || '').trim();
    if (presetId) ids.add(presetId);
    const connectorId = (connector.connector_id || '').trim();
    if (connectorId.startsWith('mcp_')) {
      ids.add(connectorId.slice('mcp_'.length));
    }
  }
  return ids;
}

export function presetAuthHint(preset: McpConnectorPreset): string {
  if (presetUsesOAuthPkce(preset)) {
    return 'Se abrirá OAuth del proveedor al confirmar.';
  }
  if (preset.auth_kind === 'bearer') {
    if (preset.preset_id === 'github') {
      return 'Pega un GitHub PAT (scopes según repos/orgs).';
    }
    const envVars = preset.metadata?.env_vars as string[] | undefined;
    if (envVars?.length) {
      return `Requiere: ${envVars.join(', ')}.`;
    }
    return 'Pega el token Bearer abajo.';
  }
  if (preset.preset_id && SECRET_ENV_PRESETS.has(preset.preset_id)) {
    const vars = preset.metadata?.secret_env as string[] | undefined;
    const list = vars?.join(', ') ?? 'connection strings';
    return `Configura los secretos de plataforma: ${list}.`;
  }
  return 'No requiere credenciales adicionales.';
}
