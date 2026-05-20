import { friendlyGatewayError } from '@/lib/adminErrors';
import type {
  AdminHealth,
  EnvConfigResponse,
  FlyCommandEntry,
  TemplateDetail,
  TemplateSummary,
  VaultBinding,
  VaultOption,
  ConsoleUser,
  SharedDbGrant,
  WhitelistUser,
} from '@/types/admin';

export interface AuditEntry {
  ts: string;
  actor: string;
  action: string;
  resource: string;
  detail: string;
  meta?: Record<string, unknown>;
}

export interface SkillCatalogItem {
  id: string;
  path: string;
  scope: string;
  worker_id?: string;
}

export interface IndustryOption {
  id: string;
  name: string;
  path: string;
}

export interface McpToolInfo {
  name: string;
  description: string;
  server: string;
}

export interface OpsCommand {
  id: string;
  label: string;
  argv: string[];
}

export interface TrainTraceFile {
  relative_path: string;
  size_bytes: number;
  line_count: number;
}

export interface TrainStatus {
  trace_format: string;
  paths: Record<string, string>;
  files: Record<string, { exists: boolean; path: string; size_bytes?: number; modified_utc?: string }>;
  conversation_traces: { file_count: number; recent: TrainTraceFile[] };
  gemma4_sanitized: { file_count: number; recent: TrainTraceFile[] };
  pipeline: { sft: string[]; grpo: string[] };
  docs: string[];
}

export interface TrainPipelineResult {
  ok: boolean;
  exit_code?: number;
  stdout?: string;
  stderr?: string;
  records?: number;
  stats?: Record<string, unknown>;
}

export interface DuckdbTableCatalog {
  vault_path: string;
  schemas: Record<string, string[]>;
}

export interface DuckdbQueryResult {
  vault_path: string;
  columns: string[];
  rows: unknown[][];
  row_count: number;
  limit_applied?: number;
}

export interface PgqGraphNode {
  id: string;
  label: string;
  group: string;
}

export interface PgqGraphLink {
  source: string;
  target: string;
  label: string;
}

export interface PgqGraphResult {
  vault_path: string;
  nodes: PgqGraphNode[];
  links: PgqGraphLink[];
  warning?: string;
}

export interface VectorMemoryHit {
  id: string;
  text: string;
  metadata: {
    source: string;
    created_at: string | null;
    embedding_status: string;
  };
  distance: number | null;
}

export interface VectorSearchResult {
  vault_path: string;
  results: VectorMemoryHit[];
  mode: 'vector' | 'lexical' | 'recent' | 'none' | string;
  warning?: string | null;
}

export interface AdminConversation {
  session_id: string;
  tenant_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  actor: string;
  section: string;
  last_worker_id: string;
  workers: string[];
  last_message_preview: string;
  message_count: number;
  origin: string;
  vault_db_path?: string;
  messages?: { role: string; content: string }[];
}

export type PlaygroundVaultInfo = {
  effective_path: string;
  scope: string;
  override_path?: string | null;
  default_path?: string | null;
};

function sessionHeaders(): HeadersInit {
  if (typeof window === 'undefined') return {};
  try {
    const raw = localStorage.getItem('duckclaw-admin-auth');
    if (!raw) return {};
    const state = JSON.parse(raw)?.state;
    const headers: Record<string, string> = {};
    if (state?.usuario?.rol) headers['x-duckclaw-role'] = String(state.usuario.rol);
    if (state?.usuario?.email) headers['x-duckclaw-actor'] = String(state.usuario.email);
    return headers;
  } catch {
    return {};
  }
}

async function adminFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`/api/admin${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...sessionHeaders(),
      ...(init?.headers ?? {}),
    },
    cache: 'no-store',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const raw =
      typeof data?.detail === 'string'
        ? data.detail
        : data?.detail?.detail ?? data?.title ?? res.statusText;
    const detail =
      data?.code === 'gateway_unreachable' || res.status === 503
        ? friendlyGatewayError(raw || 'gateway_unreachable')
        : friendlyGatewayError(raw || `Error ${res.status}`);
    throw new Error(detail);
  }
  return data as T;
}

export const adminService = {
  health: () => adminFetch<AdminHealth>('/health'),

  listTemplates: () =>
    adminFetch<{ templates: TemplateSummary[] }>('/templates').then((r) => r.templates),

  getTemplate: (id: string) => adminFetch<TemplateDetail>(`/templates/${encodeURIComponent(id)}`),

  saveTemplateFile: (workerId: string, filePath: string, content: string) =>
    adminFetch<{ ok: boolean }>(
      `/templates/${encodeURIComponent(workerId)}/files/${encodeURIComponent(filePath)}`,
      {
        method: 'PUT',
        body: JSON.stringify({ content }),
      }
    ),

  validateTemplate: (workerId: string) =>
    adminFetch<{ ok: boolean; errors: string[] }>(
      `/templates/${encodeURIComponent(workerId)}/validate`,
      { method: 'POST' }
    ),

  getTemplateVaultOptions: (workerId: string, vaultUserId?: string) => {
    const q = vaultUserId ? `?vault_user_id=${encodeURIComponent(vaultUserId)}` : '';
    return adminFetch<{ vault_user_id: string; worker_id: string; options: VaultOption[] }>(
      `/templates/${encodeURIComponent(workerId)}/vault-options${q}`
    );
  },

  getTemplateVaultBinding: (workerId: string, vaultUserId?: string) => {
    const q = vaultUserId ? `?vault_user_id=${encodeURIComponent(vaultUserId)}` : '';
    return adminFetch<{
      worker_id: string;
      vault_user_id: string;
      binding: VaultBinding | null;
      resolved_path: string | null;
    }>(`/templates/${encodeURIComponent(workerId)}/vault-binding${q}`);
  },

  putTemplateVaultBinding: (
    workerId: string,
    body: { scope: string; vault_id?: string; path?: string }
  ) =>
    adminFetch<{
      ok: boolean;
      worker_id: string;
      binding: VaultBinding | null;
      resolved_path: string | null;
    }>(`/templates/${encodeURIComponent(workerId)}/vault-binding`, {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  createTemplate: (id: string, sourceTemplate?: string) =>
    adminFetch<{ ok: boolean; id: string }>('/templates', {
      method: 'POST',
      body: JSON.stringify({ id, source_template: sourceTemplate ?? 'industries/business_standard' }),
    }),

  createProject: (body: {
    id: string;
    source_template: string;
    name: string;
    description: string;
    skills: string[];
    topology: string;
    system_prompt: string;
    soul?: string;
  }) =>
    adminFetch<{ ok: boolean; id: string; path: string }>('/projects', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  deleteTemplate: (id: string) =>
    adminFetch<{ ok: boolean }>(`/templates/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  getEnv: () => adminFetch<EnvConfigResponse>('/env'),

  patchEnv: (values: Record<string, string>) =>
    adminFetch<{ ok: boolean; updated: string[] }>('/env', {
      method: 'PATCH',
      body: JSON.stringify({ values }),
    }),

  getTelegramRoutes: () =>
    adminFetch<{
      format: string;
      routes: { bot: string; path: string; token_masked?: string }[];
      known_bots?: string[];
      parse_error?: string;
      raw_masked?: string;
      restart_hint?: string;
    }>('/telegram/routes'),

  putTelegramRoutes: (routes: { bot: string; path: string; token?: string }[]) =>
    adminFetch<{ ok: boolean; route_count: number; restart_hint?: string }>('/telegram/routes', {
      method: 'PUT',
      body: JSON.stringify({ routes }),
    }),

  getTelegramWhitelist: (tenantId: string) =>
    adminFetch<{
      tenant_id: string;
      effective_tenant_id?: string;
      requested_tenant_id?: string;
      users: WhitelistUser[];
      db_path?: string;
      warning?: string;
      hint?: string;
    }>(`/telegram/whitelist?tenant_id=${encodeURIComponent(tenantId)}`),

  upsertWhitelistUser: (body: {
    tenant_id: string;
    user_id: string;
    username?: string;
    role: string;
  }) =>
    adminFetch<{ ok: boolean }>('/telegram/whitelist', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  deleteWhitelistUser: (tenantId: string, userId: string) =>
    adminFetch<{ ok: boolean }>(
      `/telegram/whitelist?tenant_id=${encodeURIComponent(tenantId)}&user_id=${encodeURIComponent(userId)}`,
      { method: 'DELETE' }
    ),

  getAccessOverview: (tenantId: string) =>
    adminFetch<{
      tenant_id: string;
      console_users: number;
      telegram_users: number;
      shared_grants: number;
      db_path?: string;
    }>(`/access/overview?tenant_id=${encodeURIComponent(tenantId)}`),

  listConsoleUsers: () =>
    adminFetch<{ users: ConsoleUser[]; db_path?: string; warning?: string }>('/console-users'),

  upsertConsoleUser: (body: {
    email: string;
    nombre: string;
    rol: string;
    password?: string;
    initials?: string;
    active?: boolean;
  }) =>
    adminFetch<{ ok: boolean; user: ConsoleUser }>('/console-users', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  patchConsoleUser: (
    email: string,
    body: { nombre?: string; rol?: string; password?: string; initials?: string; active?: boolean }
  ) =>
    adminFetch<{ ok: boolean; user: ConsoleUser }>(
      `/console-users?email=${encodeURIComponent(email)}`,
      { method: 'PATCH', body: JSON.stringify(body) }
    ),

  deleteConsoleUser: (email: string) =>
    adminFetch<{ ok: boolean }>(`/console-users?email=${encodeURIComponent(email)}`, {
      method: 'DELETE',
    }),

  listSharedGrants: (tenantId: string) =>
    adminFetch<{ tenant_id: string; grants: SharedDbGrant[]; db_path?: string; warning?: string }>(
      `/access/shared-grants?tenant_id=${encodeURIComponent(tenantId)}`
    ),

  grantSharedAccess: (body: { tenant_id: string; user_id: string; resource_key: string }) =>
    adminFetch<{ ok: boolean }>('/access/shared-grants', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  revokeSharedAccess: (tenantId: string, userId: string, resourceKey: string) =>
    adminFetch<{ ok: boolean }>(
      `/access/shared-grants?tenant_id=${encodeURIComponent(tenantId)}&user_id=${encodeURIComponent(userId)}&resource_key=${encodeURIComponent(resourceKey)}`,
      { method: 'DELETE' }
    ),

  listFlyCommands: () =>
    adminFetch<{ header: string; commands: FlyCommandEntry[] }>(
      '/fly-commands'
    ),

  listVaults: () => adminFetch<{ vaults: { path: string; scope: string }[] }>('/runtime/vaults'),

  getDuckdbTables: (vaultPath?: string) => {
    const q = vaultPath ? `?vault_path=${encodeURIComponent(vaultPath)}` : '';
    return adminFetch<DuckdbTableCatalog>(`/duckdb/tables${q}`);
  },

  runDuckdbQuery: (body: { query: string; vault_path?: string }) =>
    adminFetch<DuckdbQueryResult>('/duckdb/query', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  getDuckdbPgqGraph: (vaultPath?: string) => {
    const q = vaultPath ? `?vault_path=${encodeURIComponent(vaultPath)}` : '';
    return adminFetch<PgqGraphResult>(`/duckdb/pgq-graph${q}`);
  },

  searchDuckdbVectorMemory: (body: { query?: string; limit?: number; vault_path?: string }) =>
    adminFetch<VectorSearchResult>('/duckdb/vector-search', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  getRuntimeConfig: (vaultPath: string, chatId: string) =>
    adminFetch<{
      rows: { key: string; value: string; scope?: string }[];
      warning?: string;
    }>(
      `/runtime/config?vault_path=${encodeURIComponent(vaultPath)}&chat_id=${encodeURIComponent(chatId)}`
    ),

  putRuntimeConfig: (body: {
    vault_path: string;
    chat_id: string;
    key: string;
    value: string;
  }) =>
    adminFetch<{ ok: boolean }>('/runtime/config', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  deleteRuntimeConfig: (vaultPath: string, chatId: string, key: string) =>
    adminFetch<{ ok: boolean }>(
      `/runtime/config?vault_path=${encodeURIComponent(vaultPath)}&chat_id=${encodeURIComponent(chatId)}&key=${encodeURIComponent(key)}`,
      { method: 'DELETE' }
    ),

  getChatHistory: (tenantId: string, sessionId: string) =>
    adminFetch<{ messages: unknown[] }>(
      `/chats/history?tenant_id=${encodeURIComponent(tenantId)}&session_id=${encodeURIComponent(sessionId)}`
    ),

  listConversations: (params?: {
    tenant_id?: string;
    section?: string;
    worker?: string;
    actor?: string;
    q?: string;
    limit?: number;
    offset?: number;
  }) => {
    const q = new URLSearchParams();
    if (params?.tenant_id) q.set('tenant_id', params.tenant_id);
    if (params?.section) q.set('section', params.section);
    if (params?.worker) q.set('worker', params.worker);
    if (params?.actor) q.set('actor', params.actor);
    if (params?.q) q.set('q', params.q);
    if (params?.limit != null) q.set('limit', String(params.limit));
    if (params?.offset != null) q.set('offset', String(params.offset));
    const qs = q.toString();
    return adminFetch<{
      tenant_id: string;
      conversations: AdminConversation[];
      total: number;
      limit: number;
      offset: number;
    }>(`/conversations${qs ? `?${qs}` : ''}`);
  },

  createConversation: (body: { title?: string; section?: string; worker_id?: string }, tenantId?: string) => {
    const q = tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : '';
    return adminFetch<AdminConversation>(`/conversations${q}`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
  },

  getConversation: (sessionId: string, tenantId?: string) => {
    const q = new URLSearchParams();
    if (tenantId) q.set('tenant_id', tenantId);
    const qs = q.toString();
    return adminFetch<AdminConversation>(
      `/conversations/${encodeURIComponent(sessionId)}${qs ? `?${qs}` : ''}`
    );
  },

  patchConversation: (sessionId: string, title: string, tenantId?: string) => {
    const q = tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : '';
    return adminFetch<AdminConversation>(`/conversations/${encodeURIComponent(sessionId)}${q}`, {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    });
  },

  deleteConversation: (sessionId: string, tenantId?: string) => {
    const q = tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : '';
    return adminFetch<{ ok: boolean; session_id: string }>(
      `/conversations/${encodeURIComponent(sessionId)}${q}`,
      { method: 'DELETE' }
    );
  },

  reindexConversations: (tenantId?: string) => {
    const q = tenantId ? `?tenant_id=${encodeURIComponent(tenantId)}` : '';
    return adminFetch<{ tenant_id: string; indexed: number; scanned: number }>(
      `/conversations/reindex${q}`,
      { method: 'POST' }
    );
  },

  getTrainStatus: () => adminFetch<TrainStatus>('/train/status'),

  getTrainTraceSample: (lake: 'conversation_traces' | 'gemma4', relativePath: string, limit = 5) =>
    adminFetch<{
      lake: string;
      relative_path: string;
      total_lines_estimate: number;
      samples: unknown[];
    }>(
      `/train/traces/sample?lake=${encodeURIComponent(lake)}&relative_path=${encodeURIComponent(relativePath)}&limit=${limit}`
    ),

  trainCollect: (requireValidSql = true) =>
    adminFetch<TrainPipelineResult>('/train/pipeline/collect', {
      method: 'POST',
      body: JSON.stringify({ require_valid_sql: requireValidSql }),
    }),

  trainSanitize: (dryRun = false) =>
    adminFetch<TrainPipelineResult>('/train/pipeline/sanitize', {
      method: 'POST',
      body: JSON.stringify({ dry_run: dryRun }),
    }),

  trainMaterialize: () =>
    adminFetch<TrainPipelineResult>('/train/pipeline/materialize', {
      method: 'POST',
      body: JSON.stringify({}),
    }),

  trainRun: (useLoraConfig = true) =>
    adminFetch<TrainPipelineResult>('/train/pipeline/run', {
      method: 'POST',
      body: JSON.stringify({ use_lora_config: useLoraConfig }),
    }),

  getAuditLog: (limit = 100) => adminFetch<{ entries: AuditEntry[] }>(`/audit?limit=${limit}`),

  getSkillsCatalog: () =>
    adminFetch<{ global: SkillCatalogItem[]; template_local: SkillCatalogItem[] }>(
      '/catalog/skills'
    ),

  getIndustriesCatalog: () =>
    adminFetch<{ industries: IndustryOption[]; starters: IndustryOption[] }>(
      '/catalog/industries'
    ),

  getSourcePreview: (sourceTemplate: string) =>
    adminFetch<{
      source_template: string;
      name: string;
      description: string;
      topology: string;
      skills: string[];
      system_prompt?: string;
      soul?: string;
    }>(`/catalog/source-preview?source_template=${encodeURIComponent(sourceTemplate)}`),

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

  getTopologiesCatalog: () =>
    adminFetch<{
      topologies: { id: string; label: string; description: string }[];
    }>('/catalog/topologies'),

  getMcpCatalog: () =>
    adminFetch<{
      duckclaw_mcp: {
        command: string;
        url: string;
        tools: McpToolInfo[];
        live?: { reachable: boolean; status_code?: number; error?: string };
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
      _gateway_stale?: boolean;
    }>('/catalog/mcp'),

  listOpsCommands: () => adminFetch<{ commands: OpsCommand[] }>('/ops/commands'),

  runOps: (opId: string) =>
    adminFetch<{
      ok: boolean;
      op_id: string;
      exit_code: number;
      stdout: string;
      stderr: string;
      executed_via?: 'local' | string;
    }>('/ops/run', { method: 'POST', body: JSON.stringify({ op_id: opId }) }),

  getComfyuiStatus: () =>
    adminFetch<{
      ok: boolean;
      url: string;
      latency_ms?: number;
      error?: string;
      system?: Record<string, unknown>;
      checkpoints?: string[];
      checkpoints_ready?: boolean;
    }>('/comfyui/status'),

  listComfyuiTemplates: () =>
    adminFetch<{
      templates: { id: string; label: string; aspect_ratios: string[] }[];
      default: string;
    }>('/comfyui/templates'),

  generateComfyuiImage: (body: {
    prompt: string;
    negative_prompt?: string;
    aspect_ratio?: string;
    template?: string;
    tenant_id?: string;
  }) =>
    fetch('/api/admin/comfyui/generate', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...sessionHeaders(),
      },
      body: JSON.stringify(body),
      cache: 'no-store',
    }).then(async (res) => {
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        const raw =
          typeof data?.detail === 'string'
            ? data.detail
            : data?.detail?.detail ?? data?.title ?? res.statusText;
        throw new Error(friendlyGatewayError(raw || `Error ${res.status}`));
      }
      return data as {
        ok: boolean;
        file_path?: string;
        artifact_id?: string;
        figure_base64?: string;
        prompt_id?: string;
        aspect_ratio?: string;
        message?: string;
        error?: string;
      };
    }),

  /** Carga imagen del vault local vía BFF (cuando figure_base64 no viene por tamaño). */
  fetchArtifactPreviewBlob: async (tenantId: string, artifactId: string) => {
    const res = await fetch(
      `/api/admin/artifacts/${encodeURIComponent(tenantId)}/${encodeURIComponent(artifactId)}`,
      { headers: sessionHeaders(), cache: 'no-store' }
    );
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      const raw =
        typeof data?.detail === 'string' ? data.detail : `Error ${res.status} al cargar imagen`;
      throw new Error(raw);
    }
    const blob = await res.blob();
    return URL.createObjectURL(blob);
  },

  getKanbanCards: () =>
    adminFetch<{ cards: import('@/lib/kanbanTypes').KanbanCard[] }>('/kanban'),

  createKanbanCard: (body: {
    title: string;
    description?: string;
    status?: import('@/lib/kanbanTypes').KanbanStatus;
    worker_id?: string;
  }) =>
    adminFetch<{ ok: boolean; card: import('@/lib/kanbanTypes').KanbanCard }>('/kanban', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  updateKanbanCard: (body: {
    id: string;
    title?: string;
    description?: string;
    status?: import('@/lib/kanbanTypes').KanbanStatus;
    worker_id?: string;
  }) =>
    adminFetch<{ ok: boolean; card: import('@/lib/kanbanTypes').KanbanCard }>('/kanban', {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),

  deleteKanbanCard: (id: string) =>
    adminFetch<{ ok: boolean }>(`/kanban?id=${encodeURIComponent(id)}`, { method: 'DELETE' }),

  getSandboxStatus: () =>
    adminFetch<{
      ready: boolean;
      hints: string[];
      docker_available: boolean;
      publish_novnc: boolean;
      public_url: string | null;
      ttl_s: number;
      browser_image: string;
      compute_image: string;
    }>('/sandbox/status'),

  getSandboxSessions: () =>
    adminFetch<{
      count: number;
      containers: {
        session_id: string;
        container_name: string;
        status: string;
        image: string;
        kind: 'browser' | 'compute' | string;
        novnc_active?: boolean;
        seconds_remaining?: number | null;
        vnc_url?: string | null;
        in_process?: boolean;
      }[];
    }>('/sandbox/sessions'),

  getSandboxChatPolicy: (params: { chatId: string; workerId?: string; tenantId?: string }) => {
    const q = new URLSearchParams();
    q.set('chat_id', params.chatId);
    if (params.workerId) q.set('worker_id', params.workerId);
    if (params.tenantId) q.set('tenant_id', params.tenantId);
    return adminFetch<{
      chat_id: string;
      worker_id: string;
      sandbox_enabled: boolean;
      sandbox_network_enabled: string | null;
      yaml_network_default: string;
      effective_network: string;
      network_toggle_available: boolean;
      browser_sandbox: boolean;
    }>(`/sandbox/chat-policy?${q.toString()}`);
  },

  setSandboxNetwork: (body: {
    chatId: string;
    enabled: boolean;
    workerId?: string;
    tenantId?: string;
  }) =>
    adminFetch<{
      ok: boolean;
      recreated: boolean;
      effective_network: string;
      network_toggle_available: boolean;
    }>('/sandbox/network', {
      method: 'POST',
      body: JSON.stringify({
        chat_id: body.chatId,
        enabled: body.enabled,
        worker_id: body.workerId,
        tenant_id: body.tenantId,
      }),
    }),

  prepareNovncSession: (body: { chatId?: string; workerId?: string; tenantId?: string }) =>
    adminFetch<{
      session_id: string;
      chat_id: string;
      worker_id: string;
      vnc_url: string;
      expires_at: number | null;
      seconds_remaining: number | null;
    }>('/sandbox/novnc/prepare', {
      method: 'POST',
      body: JSON.stringify({
        chat_id: body.chatId,
        worker_id: body.workerId,
        tenant_id: body.tenantId,
      }),
    }),

  getPlaygroundConfig: (params?: {
    telegram_user_id?: string;
    tenant_id?: string;
    chat_id?: string;
  }) => {
    const q = new URLSearchParams();
    if (params?.telegram_user_id) q.set('telegram_user_id', params.telegram_user_id);
    if (params?.tenant_id) q.set('tenant_id', params.tenant_id);
    if (params?.chat_id) q.set('chat_id', params.chat_id);
    const qs = q.toString();
    return adminFetch<{
      llm: { provider: string; model: string; base_url: string; scope?: string };
      config_chat_id?: string;
      catalog: {
        id: string;
        label: string;
        kind: string;
        env_keys: string[];
        base_url_example: string;
        model_example: string;
        hint: string;
        active?: boolean;
        keys_ok?: boolean;
      }[];
      workers: { id: string; label: string }[];
      workers_invalid?: string[];
      env_path: string;
      effective_tenant_id?: string;
      telegram_user_id?: string;
      team_chat_id?: string;
      authorized?: boolean;
      whitelist_role?: string | null;
      team_source?: string;
      team_hint?: string;
      vault?: PlaygroundVaultInfo;
      vault_options?: { path: string; scope: string; vault_id?: string; label?: string }[];
      note: string;
    }>(`/playground/config${qs ? `?${qs}` : ''}`);
  },

  setPlaygroundVault: (body: {
    chat_id: string;
    tenant_id?: string;
    vault_db_path: string;
  }) =>
    adminFetch<{
      ok: boolean;
      chat_id: string;
      tenant_id: string;
      vault_db_path: string;
      vault: PlaygroundVaultInfo;
    }>('/playground/vault', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  listForgeProjects: () =>
    adminFetch<{
      projects: {
        id: string;
        slug: string;
        display_name: string;
        coordinator?: string | null;
        members: string[];
        shared_vault_id?: string | null;
        source?: string;
        path: string;
      }[];
    }>('/forge-projects').then((r) => r.projects),

  getForgeProject: (slug: string) =>
    adminFetch<{
      id: string;
      slug: string;
      display_name: string;
      coordinator?: string | null;
      members: string[];
      shared_vault_id?: string | null;
      shared_context?: string;
      path: string;
    }>(`/forge-projects/${encodeURIComponent(slug)}`),

  createForgeProject: (body: {
    id: string;
    display_name?: string;
    members?: string[];
    coordinator?: string;
    shared_vault_id?: string;
    shared_context?: string;
    apply_tenant_team?: boolean;
    tenant_id?: string;
  }) =>
    adminFetch<{ ok: boolean; id: string; path: string; members: string[] }>('/forge-projects', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  applyForgeProjectTeam: (slug: string, tenantId = 'default') =>
    adminFetch<{ ok: boolean; tenant_id: string; members: string[] }>(
      `/forge-projects/${encodeURIComponent(slug)}/apply-team?tenant_id=${encodeURIComponent(tenantId)}`,
      { method: 'POST', body: JSON.stringify({}) }
    ),

  deleteForgeProject: (slug: string) =>
    adminFetch<{ ok: boolean; id: string }>(`/forge-projects/${encodeURIComponent(slug)}`, {
      method: 'DELETE',
    }),

  listEnvForgeProjectPresets: () =>
    adminFetch<{
      presets: {
        id: string;
        display_name: string;
        coordinator?: string | null;
        members: string[];
        shared_vault_id?: string | null;
        shared_context?: string;
      }[];
    }>('/forge-projects/env-presets').then((r) => r.presets),

  setPlaygroundModel: (body: {
    chat_id: string;
    provider: string;
    model?: string;
    base_url?: string;
  }) =>
    adminFetch<{
      ok: boolean;
      message: string;
      chat_id: string;
      llm: { provider: string; model: string; base_url: string; scope?: string };
      catalog: {
        id: string;
        label: string;
        kind: string;
        active?: boolean;
        keys_ok?: boolean;
      }[];
    }>('/playground/model', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  playgroundChat: (body: {
    worker_id: string;
    message: string;
    chat_id?: string;
    tenant_id?: string;
    telegram_user_id?: string;
    vault_db_path?: string;
    stream?: boolean;
    images?: { mime_type: string; data_base64: string }[];
  }) =>
    adminFetch<{
      ok: boolean;
      worker_id: string;
      response: string;
      assigned_worker_id?: string;
      usage_tokens?: Record<string, number>;
    }>('/playground/chat', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  /** Chat con SSE: tokens progresivos hasta evento [DONE]. */
  playgroundChatStream: async (
    body: {
      worker_id: string;
      message: string;
      chat_id?: string;
      tenant_id?: string;
      telegram_user_id?: string;
      vault_db_path?: string;
      images?: { mime_type: string; data_base64: string }[];
    },
    handlers: {
      onToken: (chunk: string) => void;
      onHeartbeat?: (payload: {
        text: string;
        kind?: 'plan' | 'tool' | 'status' | 'visual';
        worker_id?: string;
        swarm_slot?: number;
        artifact_id?: string;
        artifact_tenant_id?: string;
      }) => void;
      onDone?: (meta: {
        response: string;
        assigned_worker_id?: string;
        usage_tokens?: Record<string, number>;
        elapsed_ms?: number;
        figure_base64?: string;
        artifact_id?: string;
        artifact_tenant_id?: string;
      }) => void;
    },
    options?: { signal?: AbortSignal }
  ) => {
    const { readSseChatStream } = await import('@/lib/sseChat');
    const res = await fetch('/api/admin/playground/chat', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...sessionHeaders(),
      },
      body: JSON.stringify({ ...body, stream: true }),
      cache: 'no-store',
      signal: options?.signal,
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      const detail =
        typeof data?.detail === 'string'
          ? data.detail
          : data?.detail?.detail ?? data?.title ?? res.statusText;
      throw new Error(detail || `Error ${res.status}`);
    }
    let full = '';
    try {
      for await (const ev of readSseChatStream(res.body, options?.signal)) {
        if (options?.signal?.aborted) break;
        if (ev.type === 'token' && ev.content) {
          full += ev.content;
          handlers.onToken(ev.content);
        } else if (ev.type === 'heartbeat' && ev.text) {
          handlers.onHeartbeat?.({
            text: ev.text,
            kind: ev.kind,
            worker_id: ev.worker_id,
            swarm_slot: ev.swarm_slot,
            artifact_id: ev.artifact_id,
            artifact_tenant_id: ev.artifact_tenant_id,
          });
        } else if (ev.type === 'done') {
          handlers.onDone?.({
            response: ev.response || full,
            assigned_worker_id: ev.assigned_worker_id,
            usage_tokens: ev.usage_tokens,
            elapsed_ms: ev.elapsed_ms,
            figure_base64: ev.figure_base64,
            artifact_id: ev.artifact_id,
            artifact_tenant_id: ev.artifact_tenant_id,
          });
        } else if (ev.type === 'error') {
          throw new Error(ev.message);
        }
      }
    } catch (err) {
      if (options?.signal?.aborted || (err instanceof DOMException && err.name === 'AbortError')) {
        return full;
      }
      throw err;
    }
    if (options?.signal?.aborted) return full;
    return full;
  },
};
