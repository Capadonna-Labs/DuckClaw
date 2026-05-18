import type {
  AdminHealth,
  EnvConfigResponse,
  FlyCommandEntry,
  TemplateDetail,
  TemplateSummary,
  VaultBinding,
  VaultOption,
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
    const detail =
      typeof data?.detail === 'string'
        ? data.detail
        : data?.detail?.detail ?? data?.title ?? res.statusText;
    throw new Error(detail || `Error ${res.status}`);
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

  listFlyCommands: () =>
    adminFetch<{ header: string; commands: FlyCommandEntry[] }>(
      '/fly-commands'
    ),

  listVaults: () => adminFetch<{ vaults: { path: string; scope: string }[] }>('/runtime/vaults'),

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
      llm: { provider: string; model: string; base_url: string };
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
      workers: string[];
      env_path: string;
      effective_tenant_id?: string;
      telegram_user_id?: string;
      team_chat_id?: string;
      authorized?: boolean;
      whitelist_role?: string | null;
      team_source?: string;
      team_hint?: string;
      note: string;
    }>(`/playground/config${qs ? `?${qs}` : ''}`);
  },

  playgroundChat: (body: {
    worker_id: string;
    message: string;
    chat_id?: string;
    tenant_id?: string;
    telegram_user_id?: string;
    stream?: boolean;
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
    },
    handlers: {
      onToken: (chunk: string) => void;
      onDone?: (meta: {
        response: string;
        assigned_worker_id?: string;
        usage_tokens?: Record<string, number>;
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
        } else if (ev.type === 'done') {
          handlers.onDone?.({
            response: ev.response || full,
            assigned_worker_id: ev.assigned_worker_id,
            usage_tokens: ev.usage_tokens,
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
