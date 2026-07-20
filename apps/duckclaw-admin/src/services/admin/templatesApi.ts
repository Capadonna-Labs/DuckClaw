import type {
  TemplateDetail,
  TemplateSummary,
  VaultBinding,
  VaultOption,
} from '@/types/admin';

import { adminFetch, adminFetchOptional } from './http';

export interface UserAgentDraft {
  display_name: string;
  worker_id: string;
  description: string;
  system_prompt: string;
  soul: string;
  tool_profile: 'general' | 'minimal' | 'rag_only';
  skills: string[];
  browser_sandbox: boolean;
  web_search: boolean;
  suggested_skills: {
    name: string;
    reason: string;
    available: boolean;
  }[];
  questions: string[];
}

export interface WorkerCapabilities {
  worker_id: string;
  skills_declared: string[];
  skills_effective: string[];
  tools_runtime: string[];
  framework_baseline: boolean;
  sandbox: {
    registered: boolean;
    docker_ok: boolean;
    session_enabled: boolean | null;
  };
  optional: {
    tavily: boolean;
    browser_sandbox: boolean;
    integrations?: Record<string, boolean>;
  };
  gaps: string[];
  integration_gaps?: IntegrationGapPayload[];
}

export interface IntegrationGapPayload {
  skill: string;
  integration_id: string;
  label: string;
  setting_key: string;
  env_fallback: string;
  configured: boolean;
  admin_href: string;
  message: string;
}

export interface WorkerMcpGrantRow {
  connector_id: string;
  display_name: string;
  preset_id: string;
  enabled: boolean;
  has_auth: boolean;
  granted: boolean;
}

export interface WorkerMcpGrantsPayload {
  worker_id: string;
  connectors: WorkerMcpGrantRow[];
}

export const templatesApi = {
  listTemplates: (params?: { include_inactive?: boolean }) => {
    const q = params?.include_inactive ? '?include_inactive=true' : '';
    return adminFetch<{ templates: TemplateSummary[] }>(`/templates${q}`).then((r) => r.templates);
  },
  getTemplate: (id: string) => adminFetch<TemplateDetail>(`/templates/${encodeURIComponent(id)}`),
  patchTemplate: (workerId: string, body: { display_name: string }) =>
    adminFetch<{ ok: boolean; worker_id: string; display_name: string; task_id?: string }>(
      `/templates/${encodeURIComponent(workerId)}`,
      {
        method: 'PATCH',
        body: JSON.stringify(body),
      }
    ),
  getWorkerCapabilities: (workerId: string) =>
    adminFetchOptional<WorkerCapabilities>(
      `/workers/${encodeURIComponent(workerId)}/capabilities`
    ),
  getWorkerMcpGrants: (workerId: string) =>
    adminFetch<WorkerMcpGrantsPayload>(`/workers/${encodeURIComponent(workerId)}/mcp-grants`),
  saveTemplateFile: (workerId: string, filePath: string, content: string) =>
    adminFetch<{ ok: boolean; task_id?: string; source?: string }>(
      `/templates/${encodeURIComponent(workerId)}/files/${encodeURIComponent(filePath)}`,
      {
        method: 'PUT',
        body: JSON.stringify({ content }),
      }
    ),
  createTemplateContext: (workerId: string, body: { title: string; content_md: string; sort_order?: number }) =>
    adminFetch<{ ok: boolean; context: { context_id: string; title: string }; version: number }>(
      `/templates/${encodeURIComponent(workerId)}/contexts`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      }
    ),
  reorderTemplateContexts: (
    workerId: string,
    items: { context_id: string; sort_order: number }[]
  ) =>
    adminFetch<{ ok: boolean; updated: number }>(
      `/templates/${encodeURIComponent(workerId)}/contexts/reorder`,
      {
        method: 'PATCH',
        body: JSON.stringify({ items }),
      }
    ),
  deleteTemplateContext: (workerId: string, contextId: string) =>
    adminFetch<{ ok: boolean }>(
      `/templates/${encodeURIComponent(workerId)}/contexts/${encodeURIComponent(contextId)}`,
      { method: 'DELETE' }
    ),
  validateTemplate: (workerId: string) =>
    adminFetch<{ ok: boolean; errors: string[] }>(
      `/templates/${encodeURIComponent(workerId)}/validate`,
      { method: 'POST' }
    ),
  importTemplatesToCatalog: (body: {
    templates_root?: string;
    include_prefixes?: string[];
    include_template_ids?: string[];
  }) =>
    adminFetch<{
      ok: boolean;
      imported: { worker_id: string; worker_uid: string; template_dir: string }[];
      skipped_existing: string[];
      skipped: string[];
    }>('/templates/import', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
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
  createUserAgent: (body: {
    worker_id: string;
    display_name: string;
    source_template_id?: string;
    system_prompt?: string;
    description?: string;
    skills?: string[];
    soul?: string;
    tool_profile?: string;
    browser_sandbox?: boolean;
    web_search?: boolean;
  }) =>
    adminFetch<{
      ok: boolean;
      agent: {
        tenant_id: string;
        owner_email: string;
        worker_id: string;
        display_name: string;
        source_template_id: string;
        manifest_path: string;
        active: boolean;
      };
    }>('/user-agents', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  createUserAgentDraft: (body: { prompt: string; display_name?: string; worker_id?: string }) =>
    adminFetch<UserAgentDraft>('/user-agents/draft', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  confirmUserAgentDraft: (draft: UserAgentDraft) =>
    adminFetch<{
      ok: boolean;
      task_id: string;
      worker_id: string;
      agent: {
        tenant_id: string;
        owner_email: string;
        worker_id: string;
        display_name: string;
        source_template_id: string;
        manifest_path: string;
        active: boolean;
      };
    }>('/user-agents/draft/confirm', {
      method: 'POST',
      body: JSON.stringify({ draft }),
    }),
  deactivateTemplate: (id: string) =>
    adminFetch<{ ok: boolean }>(`/templates/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  deleteTemplate: (id: string) =>
    adminFetch<{ ok: boolean }>(`/templates/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  hardDeleteTemplate: (id: string) =>
    adminFetch<{ ok: boolean; hard_deleted: boolean }>(
      `/templates/${encodeURIComponent(id)}/hard-delete`,
      { method: 'DELETE' }
    ),
  reactivateTemplate: (id: string) =>
    adminFetch<{ ok: boolean; action: string }>(`/templates/${encodeURIComponent(id)}/reactivate`, {
      method: 'POST',
    }),
};
