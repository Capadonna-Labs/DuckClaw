import type {
  AdminHealth,
  EnvConfigResponse,
  FlyCommandEntry,
  TemplateDetail,
  TemplateSummary,
  WhitelistUser,
} from '@/types/admin';

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

  createTemplate: (id: string, sourceTemplate?: string) =>
    adminFetch<{ ok: boolean; id: string }>('/templates', {
      method: 'POST',
      body: JSON.stringify({ id, source_template: sourceTemplate ?? 'industries/business_standard' }),
    }),

  deleteTemplate: (id: string) =>
    adminFetch<{ ok: boolean }>(`/templates/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  getEnv: () => adminFetch<EnvConfigResponse>('/env'),

  patchEnv: (values: Record<string, string>) =>
    adminFetch<{ ok: boolean; updated: string[] }>('/env', {
      method: 'PATCH',
      body: JSON.stringify({ values }),
    }),

  getTelegramRoutes: () => adminFetch<{ routes: { bot: string; path: string }[] }>('/telegram/routes'),

  getTelegramWhitelist: (tenantId: string) =>
    adminFetch<{ tenant_id: string; users: WhitelistUser[]; db_path?: string; warning?: string }>(
      `/telegram/whitelist?tenant_id=${encodeURIComponent(tenantId)}`
    ),

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
    adminFetch<{ header: string; commands: FlyCommandEntry[]; leila_enabled: boolean }>(
      '/fly-commands'
    ),

  listVaults: () => adminFetch<{ vaults: { path: string; scope: string }[] }>('/runtime/vaults'),

  getRuntimeConfig: (vaultPath: string, chatId: string) =>
    adminFetch<{ rows: { key: string; value: string; scope?: string; full_key?: string }[]; warning?: string }>(
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

  getAuditLog: (limit = 100) =>
    adminFetch<{ entries: AuditEntry[] }>(`/audit?limit=${limit}`),
};

export interface AuditEntry {
  ts: string;
  actor: string;
  action: string;
  resource: string;
  detail: string;
  meta?: Record<string, unknown>;
}
