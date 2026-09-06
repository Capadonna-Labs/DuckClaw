import { readSseChatStream } from '@/lib/sseChat';
import { friendlyGatewayError } from '@/lib/adminErrors';

import { adminFetch, coalesceAdminGet, sessionHeaders } from './http';

export interface AdminConversation {
  session_id: string;
  tenant_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  actor: string;
  section: string;
  last_worker_id: string;
  /** Nombre visible del catálogo (enrich en listado; no siempre presente). */
  last_worker_display_name?: string;
  preferred_worker_id?: string;
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

export const chatApi = {
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
    const path = `/conversations${qs ? `?${qs}` : ''}`;
    return coalesceAdminGet(`GET:${path}`, () =>
      adminFetch<{
        tenant_id: string;
        conversations: AdminConversation[];
        total: number;
        limit: number;
        offset: number;
      }>(path)
    );
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
    const path = `/conversations/${encodeURIComponent(sessionId)}${qs ? `?${qs}` : ''}`;
    return coalesceAdminGet(`GET:${path}`, () => adminFetch<AdminConversation>(path));
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
    const path = `/playground/config${qs ? `?${qs}` : ''}`;
    return coalesceAdminGet(`GET:${path}`, () =>
      adminFetch<{
        llm: { provider: string; model: string; base_url: string; scope?: string };
        llm_gap?: {
          provider: string;
          label: string;
          message: string;
          admin_href: string;
          integration_id?: string;
        } | null;
        slm?: {
          enabled: boolean;
          model: string;
          model_short?: string;
          adapter_path: string;
          base_url: string;
          mlx_status: 'online' | 'offline' | 'unknown';
          pm2_name: string;
          adapters: { id: string; label: string; path: string; active?: boolean }[];
          hint?: string;
          scope?: string;
        };
        config_chat_id?: string;
        knowledge_scope?: string;
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
        projects?: {
          project_id: string;
          name: string;
          description: string;
          agent_count?: number;
          agents: {
            worker_uid: string;
            worker_id: string;
            display_name: string;
            role: string;
            sort_order: string;
          }[];
        }[];
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
        selected_worker_id?: string;
        voice?: {
          configured: boolean;
          available: boolean;
          tts_loaded: boolean;
        };
        realtime_voice?: {
          configured: boolean;
          available: boolean;
          transport: string;
        };
        note: string;
      }>(path)
    );
  },

  getChatSuggestions: (body: {
    chat_id: string;
    tenant_id?: string;
    last_user_message: string;
    last_assistant_message: string;
  }) =>
    adminFetch<{ suggestions: string[] }>('/chat/suggestions', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  setPlaygroundWorker: (body: {
    chat_id: string;
    tenant_id?: string;
    worker_id: string;
  }) =>
    adminFetch<{
      ok: boolean;
      chat_id: string;
      tenant_id: string;
      worker_id: string;
      selected_worker_id: string;
      effective_worker_id: string;
    }>('/playground/worker', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

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

  setPlaygroundKnowledgeScope: (body: {
    chat_id: string;
    tenant_id?: string;
    knowledge_scope: string;
    project_id?: string;
  }) =>
    adminFetch<{
      ok: boolean;
      chat_id: string;
      tenant_id: string;
      knowledge_scope: string;
      project_id?: string | null;
      message: string;
    }>('/playground/knowledge-scope', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

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

  setPlaygroundSlm: (body: {
    chat_id: string;
    enabled: boolean;
    adapter_path?: string;
  }) =>
    adminFetch<{
      ok: boolean;
      message: string;
      chat_id: string;
      slm: {
        enabled: boolean;
        model: string;
        model_short?: string;
        adapter_path: string;
        base_url: string;
        mlx_status: 'online' | 'offline' | 'unknown';
        pm2_name: string;
        adapters: { id: string; label: string; path: string; active?: boolean }[];
        hint?: string;
      };
    }>('/playground/slm', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  playgroundChat: (body: {
    worker_id: string;
    project_id?: string;
    knowledge_scope?: string;
    message: string;
    chat_id?: string;
    tenant_id?: string;
    telegram_user_id?: string;
    vault_db_path?: string;
    stream?: boolean;
    images?: { mime_type: string; data_base64: string }[];
    documents?: { filename: string; mime_type: string; data_base64: string }[];
  }) =>
    adminFetch<{
      ok: boolean;
      worker_id: string;
      response: string;
      assigned_worker_id?: string;
      usage_tokens?: Record<string, number>;
      rag_context_count?: number;
    }>('/playground/chat', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  /** Interrumpe un turno de chat admin en curso (flag Redis en gateway). */
  playgroundChatCancel: async (chat_id: string) =>
    adminFetch<{ ok: boolean; chat_id: string; cancelled?: boolean }>(
      '/playground/chat/cancel',
      {
        method: 'POST',
        body: JSON.stringify({ chat_id }),
      }
    ),

  /** Chat con SSE: tokens progresivos hasta evento [DONE]. */
  playgroundChatStream: async (
    body: {
      worker_id: string;
      project_id?: string;
      knowledge_scope?: string;
      message: string;
      chat_id?: string;
      tenant_id?: string;
      telegram_user_id?: string;
      vault_db_path?: string;
      images?: { mime_type: string; data_base64: string }[];
      documents?: { filename: string; mime_type: string; data_base64: string }[];
      voice_response?: boolean;
    },
    handlers: {
      onToken: (chunk: string) => void;
      onAudio?: (payload: {
        audio_base64?: string;
        audio_unavailable?: boolean;
        audio_format?: 'ogg' | 'wav';
      }) => void;
      onHeartbeat?: (payload: {
        text: string;
        kind?: 'plan' | 'tool' | 'status' | 'visual';
        worker_id?: string;
        swarm_slot?: number;
        artifact_id?: string;
        artifact_tenant_id?: string;
        sandbox_run_id?: string;
        artifact_ids?: string[];
        tool_name?: string;
        tool_phase?: 'start' | 'done' | 'error';
        elapsed_ms?: number;
      }) => void;
      onDone?: (meta: {
        response: string;
        assigned_worker_id?: string;
        usage_tokens?: Record<string, number>;
        context_estimated_tokens?: number;
        elapsed_ms?: number;
        figure_base64?: string;
        fly_charts_b64?: string[];
        fly_chart_artifact_ids?: string[];
        fly_chart_names?: string[];
        artifact_id?: string;
        artifact_tenant_id?: string;
      }) => void;
    },
    options?: { signal?: AbortSignal }
  ) => {
    let res: Response;
    try {
      res = await fetch('/api/admin/playground/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...sessionHeaders('POST'),
        },
        credentials: 'include',
        body: JSON.stringify({ ...body, stream: true }),
        cache: 'no-store',
        signal: options?.signal,
      });
    } catch (err) {
      if (options?.signal?.aborted || (err instanceof DOMException && err.name === 'AbortError')) {
        return '';
      }
      const raw = err instanceof Error ? err.message : 'Error de red';
      throw new Error(friendlyGatewayError(raw));
    }
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
            sandbox_run_id: ev.sandbox_run_id,
            artifact_ids: ev.artifact_ids,
            tool_name: ev.tool_name,
            tool_phase: ev.tool_phase,
            elapsed_ms: ev.elapsed_ms,
          });
        } else if (ev.type === 'done') {
          handlers.onDone?.({
            response: ev.response || full,
            assigned_worker_id: ev.assigned_worker_id,
            usage_tokens: ev.usage_tokens,
            context_estimated_tokens: ev.context_estimated_tokens,
            elapsed_ms: ev.elapsed_ms,
            figure_base64: ev.figure_base64,
            fly_charts_b64: ev.fly_charts_b64,
            fly_chart_artifact_ids: ev.fly_chart_artifact_ids,
            fly_chart_names: ev.fly_chart_names,
            artifact_id: ev.artifact_id,
            artifact_tenant_id: ev.artifact_tenant_id,
          });
        } else if (ev.type === 'audio') {
          handlers.onAudio?.({
            audio_base64: ev.audio_base64,
            audio_unavailable: ev.audio_unavailable,
            audio_format: ev.audio_format,
          });
        } else if (ev.type === 'error') {
          throw new Error(ev.message);
        }
      }
    } catch (err) {
      if (options?.signal?.aborted || (err instanceof DOMException && err.name === 'AbortError')) {
        return full;
      }
      const raw = err instanceof Error ? err.message : 'Error';
      throw new Error(friendlyGatewayError(raw));
    }
    if (options?.signal?.aborted) return full;
    return full;
  },
};
