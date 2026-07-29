import { adminFetch, coalesceAdminGet } from './http';

export interface SandboxArtifactMeta {
  artifact_id: string;
  filename: string;
  relative_path: string;
  mime: string;
  byte_size: number;
  previewable: boolean;
}

export interface SandboxRunSummary {
  run_id: string;
  chat_id?: string;
  chat_session_id?: string;
  tenant_id?: string;
  worker_id?: string;
  created_at?: number;
  expires_at?: number;
  exit_code?: number;
  artifact_count: number;
}

export interface SandboxRunDetail {
  run_id: string;
  chat_id?: string;
  chat_session_id?: string;
  tenant_id?: string;
  worker_id?: string;
  created_at?: number;
  expires_at?: number;
  exit_code?: number;
  artifacts: SandboxArtifactMeta[];
}

export type SandboxArtifactPreviewPayload = {
  preview_kind: 'markdown' | 'text' | 'json' | 'tabular' | 'parquet' | 'csv';
  mime?: string;
  content?: string;
  truncated?: boolean;
  valid_json?: boolean;
  columns?: string[];
  rows?: unknown[][];
  schema?: { name: string; type: string }[];
  row_count_shown?: number;
  source_ext?: string;
};

export const sandboxApi = {
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

  getSandboxChatPolicy: (params: {
    chatId: string;
    workerId?: string;
    tenantId?: string;
    vaultDbPath?: string;
  }) => {
    const q = new URLSearchParams();
    q.set('chat_id', params.chatId);
    if (params.workerId) q.set('worker_id', params.workerId);
    if (params.tenantId) q.set('tenant_id', params.tenantId);
    if (params.vaultDbPath) q.set('vault_db_path', params.vaultDbPath);
    const path = `/sandbox/chat-policy?${q.toString()}`;
    return coalesceAdminGet(`GET:${path}`, () =>
      adminFetch<{
        chat_id: string;
        worker_id: string;
        sandbox_enabled: boolean;
        sandbox_network_enabled: string | null;
        yaml_network_default: string;
        effective_network: string;
        network_toggle_available: boolean;
        browser_sandbox: boolean;
      }>(path)
    );
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

  listSandboxRuns: (chatId: string, limit = 20) => {
    const q = new URLSearchParams();
    q.set('chat_id', chatId);
    q.set('limit', String(limit));
    return adminFetch<{ runs: SandboxRunSummary[]; count: number }>(
      `/sandbox/artifacts/runs?${q.toString()}`
    );
  },

  listAllSandboxRuns: (limit = 50) => {
    const q = new URLSearchParams();
    q.set('limit', String(limit));
    return adminFetch<{ runs: SandboxRunSummary[]; count: number; scope: string }>(
      `/sandbox/artifacts/runs?${q.toString()}`
    );
  },

  getSandboxRun: async (runId: string, chatId: string) => {
    const q = new URLSearchParams();
    q.set('chat_id', chatId);
    const res = await adminFetch<{ run: SandboxRunDetail }>(
      `/sandbox/artifacts/runs/${encodeURIComponent(runId)}?${q.toString()}`
    );
    return res.run;
  },

  sandboxArtifactPreviewUrl: (artifactId: string, chatId: string) => {
    const q = new URLSearchParams();
    if (chatId.trim()) q.set('chat_id', chatId);
    const qs = q.toString();
    return `/api/admin/sandbox-artifacts/${encodeURIComponent(artifactId)}/preview${qs ? `?${qs}` : ''}`;
  },

  sandboxArtifactDownloadUrl: (artifactId: string, chatId: string) => {
    const q = new URLSearchParams();
    if (chatId.trim()) q.set('chat_id', chatId);
    return `/api/admin/sandbox-artifacts/${encodeURIComponent(artifactId)}/download?${q.toString()}`;
  },

  deleteSandboxArtifact: (artifactId: string, chatId = '') => {
    const q = new URLSearchParams();
    if (chatId.trim()) q.set('chat_id', chatId);
    const qs = q.toString();
    return adminFetch<{ deleted: boolean; run_removed?: boolean }>(
      `/sandbox/artifacts/${encodeURIComponent(artifactId)}${qs ? `?${qs}` : ''}`,
      { method: 'DELETE' }
    );
  },

  deleteSandboxRun: (runId: string, chatId: string) => {
    const q = new URLSearchParams();
    q.set('chat_id', chatId);
    return adminFetch<{ deleted: boolean }>(
      `/sandbox/artifacts/runs/${encodeURIComponent(runId)}?${q.toString()}`,
      { method: 'DELETE' }
    );
  },

  saveSandboxArtifactToVault: (body: {
    artifactId: string;
    chatId?: string;
    relativeDest?: string;
    syncRag?: boolean;
    tenantId?: string;
    projectId?: string;
  }) =>
    adminFetch<{
      ok: boolean;
      relative_path: string;
      path: string;
      rag_sync?: Record<string, unknown>;
    }>(`/sandbox/artifacts/${encodeURIComponent(body.artifactId)}/save-to-vault`, {
      method: 'POST',
      body: JSON.stringify({
        chat_id: body.chatId ?? '',
        relative_dest: body.relativeDest ?? '',
        sync_rag: body.syncRag ?? true,
        tenant_id: body.tenantId,
        project_id: body.projectId,
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
    })
};
