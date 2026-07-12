import { friendlyGatewayError, parseApiErrorDetail } from '@/lib/adminErrors';
import { mutationHeaders } from '@/lib/csrfClient';
import { readSseChatStream } from '@/lib/sseChat';
import type {
  AdminHealth,
  ReleaseWorkerCacheResult,
  FlyCommandEntry,
  TemplateDetail,
  TemplateSummary,
  VaultBinding,
  VaultOption,
  ConsoleUser,
  OverviewMetrics,
  OverviewMetricsParams,
  RestoreFrameworkPoliciesResponse,
  SharedDbGrant,
  SyncCatalogPromptsResponse,
  WhitelistUser,
  WorkerCapabilitiesPayload,
  WriteTaskStatusResponse,
} from '@/types/admin';

export type { TemplateSummary, TemplateDetail } from '@/types/admin';

export interface McpConnectorSummary {
  connector_id: string;
  tenant_id: string;
  display_name: string;
  transport: string;
  endpoint_url?: string;
  launch_command?: string;
  launch_args?: string[];
  auth_kind: string;
  has_auth: boolean;
  tool_allowlist: string[];
  tool_denylist: string[];
  read_only: boolean;
  egress_hosts: string[];
  preset_id?: string;
  enabled: boolean;
  active: boolean;
  metadata?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
}

export interface McpConnectorPreset {
  preset_id: string;
  display_name: string;
  transport: string;
  endpoint_url?: string;
  launch_command?: string;
  launch_args?: string[];
  auth_kind: string;
  read_only: boolean;
  egress_hosts: string[];
  tool_allowlist: string[];
  tool_denylist: string[];
  metadata?: Record<string, unknown>;
}

export interface McpConnectorTestResult {
  ok: boolean;
  connector_id: string;
  transport: string;
  tool_count: number;
  tools: { name: string; description?: string }[];
  error?: string;
}

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

export interface SkillCategorySkillItem {
  id: string;
  label: string;
  hint?: string | null;
}

export interface SkillCategoryPayload {
  id: string;
  title: string;
  description?: string | null;
  read_only?: boolean;
  skills: SkillCategorySkillItem[];
}

export interface SkillCategoriesCatalogResponse {
  categories: SkillCategoryPayload[];
  baseline_profiles: Record<string, string[]>;
  pack_version?: string;
}

export interface IntegrationCatalogItem {
  id: string;
  setting_key: string;
  domain: string;
  label: string;
  description: string;
  env_fallback: string;
  env_keys: string[];
  related_skills: string[];
  docs_url?: string | null;
  default_scope: 'tenant' | 'global' | 'actor';
  configured: boolean;
  source: string;
}

export interface IntegrationCatalogGroup {
  id: string;
  title: string;
  description: string;
  sort_order: number;
  integrations: IntegrationCatalogItem[];
}

export interface IntegrationCatalogResponse {
  pack_version: string;
  pack_source?: string;
  tenant_id: string;
  actor_email: string;
  groups: IntegrationCatalogGroup[];
  integrations: IntegrationCatalogItem[];
}

export interface CreateSkillInput {
  name: string;
  description?: string;
  skill_type?: string;
  implementation_ref: string;
  visibility?: 'private' | 'public';
}

export interface ReportSectionProgress {
  id: string;
  label: string;
  status: string;
}

export interface ReportInstanceProgress {
  section_count: number;
  complete_count: number;
  partial_count: number;
  missing_count: number;
  completion_percent: number;
  missing_sections: ReportSectionProgress[];
  partial_sections: ReportSectionProgress[];
  complete_sections: string[];
}

export interface ReportInstanceSummary {
  instance_id: string;
  template_id: string;
  template_name: string;
  title: string;
  period_key: string;
  project_id: string;
  status: string;
  preview_html: string;
  rendered_docx_uri: string;
  conversation_id: string;
  updated_at: string;
  progress: ReportInstanceProgress;
}

export interface ReportInstanceDetail {
  instance: {
    instance_id: string;
    template_id: string;
    tenant_id: string;
    owner_email: string;
    project_id: string;
    title: string;
    period_key: string;
    state: Record<string, unknown>;
    status: string;
    preview_html: string;
    rendered_docx_uri: string;
    conversation_id: string;
  };
  template_name: string;
  progress: ReportInstanceProgress;
}

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
  preview_kind: 'markdown' | 'text' | 'json' | 'tabular' | 'parquet';
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

export interface ManagedWorkspaceDraft {
  project: {
    name: string;
    description: string;
  };
  workers: {
    worker_id: string;
    display_name: string;
    role: string;
    system_prompt: string;
  }[];
  shared_context: string;
  suggested_skills: {
    name: string;
    reason: string;
    available: boolean;
  }[];
  questions: string[];
}

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

export interface PromptPolicy {
  policy_id: string;
  policy_type: string;
  policy_name: string;
  version: number;
  status: string;
  content: string;
  checksum: string;
  metadata?: Record<string, unknown>;
  active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface PromptPolicyRequirement {
  policy_type: string;
  policy_name: string;
  source: string;
}

export interface PromptPolicyHealth {
  ok: boolean;
  checked_count: number;
  missing_count: number;
  inherited_count: number;
  requirements: PromptPolicyRequirement[];
  missing: PromptPolicyRequirement[];
  inherited: Array<PromptPolicyRequirement & { warning: string }>;
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

export interface PromptPolicyUpsertInput {
  policy_type: string;
  policy_name: string;
  version: number;
  status?: string;
  content: string;
  metadata?: Record<string, unknown>;
}

export interface WorkspaceProjectSummary {
  project_id: string;
  tenant_id: string;
  owner_email: string;
  name: string;
  description: string;
  status: string;
  visibility: string;
  created_at?: string;
  updated_at?: string;
  agent_count?: number;
  agents?: {
    worker_uid: string;
    worker_id: string;
    display_name: string;
    role: string;
    sort_order: string;
  }[];
}

export interface WorkspaceProjectsQuery {
  /** q: search text for name, description or project id. */
  q?: string;
  status?: string;
  sort?: 'updated_at' | 'created_at' | 'name' | 'agent_count';
  direction?: 'asc' | 'desc';
  /** limit: maximum number of projects to return. */
  limit?: number;
  /** offset: zero-based pagination offset. */
  offset?: number;
}

export interface WorkspaceProjectsPage {
  projects: WorkspaceProjectSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface KnowledgeSource {
  source_id: string;
  tenant_id: string;
  project_id: string;
  worker_uid: string;
  source_kind: string;
  source_uri: string;
  display_name: string;
  status: string;
  metadata?: Record<string, unknown>;
  active: boolean;
  created_at?: string;
  updated_at?: string;
  document_count: number;
  chunk_count: number;
  document_paths?: string;
}

export type KnowledgeBrowseEntry = {
  name: string;
  path: string;
  kind: 'root' | 'directory';
  exists: boolean;
  selectable: boolean;
};

export type KnowledgeBrowseResponse = {
  path: string;
  parent_path: string | null;
  roots_mode: boolean;
  entries: KnowledgeBrowseEntry[];
};

export interface KnowledgeSearchResult {
  chunk_id: string;
  source_id: string;
  document_id: string;
  relative_path: string;
  chunk_index: number;
  text: string;
  score?: number | null;
  match_type: 'vector' | 'lexical';
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
  vault_user_id?: string;
  actor_email?: string;
  tenant_id?: string;
  table_count?: number;
  schemas: Record<string, string[]>;
}

export interface DuckdbLegacySchema {
  schema: string;
  table_count: number;
  tables: string[];
}

export interface DuckdbLegacyMainTable {
  schema: 'main';
  table: string;
}

export interface DuckdbLegacySchemasResponse {
  vault_path: string;
  vault_user_id?: string;
  actor_email?: string;
  tenant_id?: string;
  schemas: DuckdbLegacySchema[];
  main_tables: DuckdbLegacyMainTable[];
  confirm: string;
}

export interface DuckdbQueryResult {
  vault_path: string;
  vault_user_id?: string;
  actor_email?: string;
  tenant_id?: string;
  mode?: 'read' | 'write';
  status?: string;
  task_id?: string;
  columns: string[];
  rows: unknown[][];
  row_count: number;
  limit_applied?: number;
  offset?: number;
  has_more?: boolean;
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

export interface CodeDecisionRow {
  id: string;
  repo: string;
  file_path: string;
  branch_name: string;
  decision_type: string;
  title: string;
  status: string;
  created_at?: string;
  pr_url?: string;
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

function sessionHeaders(method = 'GET'): HeadersInit {
  return mutationHeaders(method);
}

async function adminFetchOptional<T>(path: string, init?: RequestInit): Promise<T | null> {
  const method = init?.method || 'GET';
  const res = await fetch(`/api/admin${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...sessionHeaders(method),
      ...(init?.headers ?? {}),
    },
    cache: 'no-store',
  });
  if (res.status === 404) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const raw = parseApiErrorDetail(data, res.status);
    const detail =
      data?.code === 'gateway_unreachable' || res.status === 503
        ? friendlyGatewayError(raw || 'gateway_unreachable')
        : friendlyGatewayError(raw || `Error ${res.status}`);
    throw new Error(detail);
  }
  return data as T;
}

async function adminFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const method = init?.method || 'GET';
  const res = await fetch(`/api/admin${path}`, {
    ...init,
    credentials: 'include',
    headers: {
      'Content-Type': 'application/json',
      ...sessionHeaders(method),
      ...(init?.headers ?? {}),
    },
    cache: 'no-store',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const raw = parseApiErrorDetail(data, res.status);
    const detail =
      data?.code === 'gateway_unreachable' || res.status === 503
        ? friendlyGatewayError(raw || 'gateway_unreachable')
        : friendlyGatewayError(raw || `Error ${res.status}`);
    throw new Error(detail);
  }
  return data as T;
}

async function adminFormFetch<T>(path: string, formData: FormData, method = 'POST'): Promise<T> {
  const res = await fetch(`/api/admin${path}`, {
    method,
    credentials: 'include',
    headers: {
      ...sessionHeaders(method),
    },
    body: formData,
    cache: 'no-store',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const raw = parseApiErrorDetail(data, res.status);
    throw new Error(friendlyGatewayError(raw || `Error ${res.status}`));
  }
  return data as T;
}

function workspaceProjectsQueryString(params?: WorkspaceProjectsQuery): string {
  const qs = new URLSearchParams();
  if (params?.q) qs.set('q', params.q);
  if (params?.status) qs.set('status', params.status);
  if (params?.sort) qs.set('sort', params.sort);
  if (params?.direction) qs.set('direction', params.direction);
  if (params?.limit != null) qs.set('limit', String(params.limit));
  if (params?.offset != null) qs.set('offset', String(params.offset));
  const suffix = qs.toString();
  return suffix ? `?${suffix}` : '';
}

function promptPoliciesQueryString(params?: {
  policy_type?: string;
  policy_name?: string;
  include_inactive?: boolean;
}): string {
  const qs = new URLSearchParams();
  if (params?.policy_type) qs.set('policy_type', params.policy_type);
  if (params?.policy_name) qs.set('policy_name', params.policy_name);
  if (params?.include_inactive) qs.set('include_inactive', 'true');
  const suffix = qs.toString();
  return suffix ? `?${suffix}` : '';
}

function listWorkspaceProjectsPage(params?: WorkspaceProjectsQuery) {
  return adminFetch<WorkspaceProjectsPage>(`/workspace/projects${workspaceProjectsQueryString(params)}`);
}

export const adminService = {
  health: () => adminFetch<AdminHealth>('/health'),

  releaseWorkerGraphCache: () =>
    adminFetch<ReleaseWorkerCacheResult>('/gateway/release-worker-cache', { method: 'POST' }),

  listPromptPolicies: (params?: {
    policy_type?: string;
    policy_name?: string;
    include_inactive?: boolean;
  }) =>
    adminFetch<{ policies: PromptPolicy[] }>(`/prompt-policies${promptPoliciesQueryString(params)}`).then(
      (r) => r.policies
    ),

  upsertPromptPolicy: (body: PromptPolicyUpsertInput) =>
    adminFetch<{
      ok: boolean;
      task_id: string;
      policy: {
        policy_id: string;
        policy_type: string;
        policy_name: string;
        version: number;
        status: string;
        active: boolean;
      };
    }>('/prompt-policies', {
      method: 'PUT',
      body: JSON.stringify(body),
    }),

  deactivatePromptPolicy: (policyType: string, policyName: string, version: number) =>
    adminFetch<{
      ok: boolean;
      task_id: string;
      policy_type: string;
      policy_name: string;
      version: number;
    }>(
      `/prompt-policies/${encodeURIComponent(policyType)}/${encodeURIComponent(policyName)}?version=${encodeURIComponent(String(version))}`,
      { method: 'DELETE' }
    ),

  getPromptPolicyHealth: () => adminFetch<PromptPolicyHealth>('/prompt-policies/health'),

  restoreFrameworkPolicies: () =>
    adminFetch<RestoreFrameworkPoliciesResponse>('/prompt-policies/restore-framework', {
      method: 'POST',
    }),

  syncCatalogPrompts: (force = false) =>
    adminFetch<SyncCatalogPromptsResponse>(
      `/prompt-policies/sync-catalog?force=${force ? 'true' : 'false'}`,
      { method: 'POST' }
    ),

  getWriteTaskStatus: (taskId: string) =>
    adminFetch<WriteTaskStatusResponse>(`/write-tasks/${encodeURIComponent(taskId)}`),

  getOverviewMetrics: (params?: OverviewMetricsParams) => {
    const qs = new URLSearchParams();
    if (params?.usage_days != null) qs.set('usage_days', String(params.usage_days));
    if (params?.usage_group_by) qs.set('usage_group_by', params.usage_group_by);
    if (params?.worker_id) qs.set('worker_id', params.worker_id);
    if (params?.session_id) qs.set('session_id', params.session_id);
    const suffix = qs.toString() ? `?${qs.toString()}` : '';
    return adminFetch<OverviewMetrics>(`/overview/metrics${suffix}`);
  },

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

  getRuntimeSettings: (params?: { domains?: string[] }) => {
    const q = new URLSearchParams();
    params?.domains?.forEach((domain) => q.append('domain', domain));
    const qs = q.toString();
    return adminFetch<{
      tenant_id: string;
      actor_email: string;
      settings: {
        setting_id: string;
        tenant_id: string;
        actor_email: string;
        domain: string;
        key: string;
        value_kind: string;
        secret: boolean;
        source: string;
        configured: boolean;
        value_text?: string;
        value_json?: unknown;
        masked_value?: string;
        updated_at: string;
      }[];
    }>(`/settings/runtime${qs ? `?${qs}` : ''}`);
  },

  patchRuntimeSettings: (settings: {
    domain: string;
    key: string;
    value: unknown;
    scope?: 'actor' | 'tenant' | 'global';
    value_kind?: string;
    secret?: boolean;
  }[]) =>
    adminFetch<{ ok: boolean; updated: string[]; task_id?: string; task_ids?: string[] }>(
      '/settings/runtime', {
      method: 'PATCH',
      body: JSON.stringify({ settings }),
    }),

  getTelegramRoutes: () =>
    adminFetch<{
      format: string;
      source?: string;
      runtime_key?: string;
      routes: {
        bot: string;
        path: string;
        worker_id?: string;
        tenant_id?: string;
        vault_env_var?: string;
        token_masked?: string;
      }[];
      known_bots?: string[];
      parse_error?: string;
      raw_masked?: string;
      restart_hint?: string;
    }>('/telegram/routes'),

  putTelegramRoutes: (routes: {
    bot: string;
    path: string;
    worker_id: string;
    tenant_id: string;
    vault_env_var?: string;
    token?: string;
  }[]) =>
    adminFetch<{ ok: boolean; updated?: string[]; source?: string; route_count: number; restart_hint?: string }>('/telegram/routes', {
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
      db_exists?: boolean;
      persistence_tables?: {
        console: string;
        telegram: string;
        shared: string;
      };
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

  listDuckdbLegacySchemas: (vaultPath?: string) => {
    const q = vaultPath ? `?vault_path=${encodeURIComponent(vaultPath)}` : '';
    return adminFetch<DuckdbLegacySchemasResponse>(`/duckdb/legacy-schemas${q}`);
  },

  dropDuckdbLegacySchemas: (body: {
    schemas: string[];
    main_tables?: string[];
    vault_path?: string;
    confirm: string;
  }) =>
    adminFetch<{
      ok: boolean;
      dropped: string[];
      dropped_main_tables: string[];
      vault_path: string;
    }>('/duckdb/legacy-schemas/drop', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  runDuckdbQuery: (body: {
    query: string;
    vault_path?: string;
    limit?: number;
    offset?: number;
  }) =>
    adminFetch<DuckdbQueryResult>('/duckdb/query', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  listCodeDecisions: (vaultPath: string, status = 'PENDING_HITL', limit = 20) => {
    const q = new URLSearchParams({
      vault_path: vaultPath,
      status,
      limit: String(limit),
    });
    return adminFetch<{ items: CodeDecisionRow[]; status_filter: string }>(`/code/decisions?${q}`);
  },

  approveCodeDecision: (body: {
    decision_id: string;
    vault_path: string;
    chat_id?: string;
    tenant_id?: string;
    user_id?: string;
  }) =>
    adminFetch<{ status: string; pr_url?: string; decision_id: string }>('/code/approve', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  rejectCodeDecision: (body: {
    decision_id: string;
    vault_path: string;
    rationale?: string;
    tenant_id?: string;
    user_id?: string;
  }) =>
    adminFetch<{ status: string; decision_id: string }>('/code/reject', {
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

  getSkillCategories: () =>
    adminFetch<SkillCategoriesCatalogResponse>('/catalog/skill-categories'),

  getIntegrationCatalog: () => adminFetch<IntegrationCatalogResponse>('/integrations/catalog'),

  createSkill: (body: CreateSkillInput) =>
    adminFetch<{ ok: boolean; skill: SkillCatalogItem }>('/catalog/skills', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  hardDeleteSkill: (name: string) =>
    adminFetch<{ ok: boolean; hard_deleted: boolean; id: string }>(
      `/catalog/skills/${encodeURIComponent(name)}/hard-delete`,
      { method: 'DELETE' }
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

  listMcpConnectors: () =>
    adminFetch<{ connectors: McpConnectorSummary[] }>('/mcp/connectors').then((r) => r.connectors),

  listMcpConnectorPresets: () =>
    adminFetch<{ presets: McpConnectorPreset[] }>('/mcp/connectors/presets').then((r) => r.presets),

  createMcpConnector: (body: { preset_id: string; connector_id?: string; display_name?: string }) =>
    adminFetch<{ ok: boolean; task_id: string; connector: McpConnectorSummary | null }>(
      '/mcp/connectors',
      {
        method: 'POST',
        body: JSON.stringify(body),
      }
    ),

  setMcpConnectorAuth: (connectorId: string, bearerToken: string) =>
    adminFetch<{ ok: boolean; task_id: string }>(`/mcp/connectors/${encodeURIComponent(connectorId)}/auth`, {
      method: 'POST',
      body: JSON.stringify({ bearer_token: bearerToken }),
    }),

  startMcpConnectorOAuth: (connectorId: string, redirectUri?: string) =>
    adminFetch<{ ok: boolean; authorization_url: string; state: string; redirect_uri: string }>(
      `/mcp/connectors/${encodeURIComponent(connectorId)}/oauth/start`,
      {
        method: 'POST',
        body: JSON.stringify({ redirect_uri: redirectUri || '' }),
      }
    ),

  testMcpConnector: (connectorId: string) =>
    adminFetch<McpConnectorTestResult>(`/mcp/connectors/${encodeURIComponent(connectorId)}/test`, {
      method: 'POST',
    }),

  grantMcpConnector: (connectorId: string, workerId: string) =>
    adminFetch<{ ok: boolean; task_id: string; worker_id: string; worker_uid: string }>(
      `/mcp/connectors/${encodeURIComponent(connectorId)}/grants`,
      {
        method: 'POST',
        body: JSON.stringify({ worker_id: workerId }),
      }
    ),

  revokeMcpConnectorGrant: (connectorId: string, workerId: string) =>
    adminFetch<{ ok: boolean; task_id: string }>(
      `/mcp/connectors/${encodeURIComponent(connectorId)}/grants/${encodeURIComponent(workerId)}`,
      { method: 'DELETE' }
    ),

  deactivateMcpConnector: (connectorId: string) =>
    adminFetch<{ ok: boolean; task_id: string }>(`/mcp/connectors/${encodeURIComponent(connectorId)}`, {
      method: 'DELETE',
    }),

  getMcpCatalog: () =>
    adminFetch<{
      duckclaw_mcp: {
        command: string;
        url: string;
        port?: string;
        source?: string;
        runtime_key?: string;
        tools: McpToolInfo[];
        live?: { reachable: boolean; status_code?: number; error?: string; port?: string; url?: string };
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
      source?: string;
      runtime_key?: string;
      timeout_sec?: string;
      timeout_source?: string;
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
        ...sessionHeaders('POST'),
      },
      credentials: 'include',
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
      { headers: sessionHeaders('GET'), credentials: 'include', cache: 'no-store' }
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
    }>(`/playground/config${qs ? `?${qs}` : ''}`);
  },

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

  listWorkspaceProjectsPage,

  listWorkspaceProjects: () =>
    listWorkspaceProjectsPage().then((r) => r.projects),

  createWorkspaceProject: (body: { name: string; description?: string; visibility?: string }) =>
    adminFetch<{
      ok: boolean;
      project: {
        project_id: string;
        tenant_id: string;
        owner_email: string;
        name: string;
        description: string;
        status: string;
        visibility: string;
      };
    }>('/workspace/projects', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  getWorkspaceProject: (projectId: string) =>
    adminFetch<{
      project: WorkspaceProjectSummary;
      agents: NonNullable<WorkspaceProjectSummary['agents']>;
    }>(`/workspace/projects/${encodeURIComponent(projectId)}`),

  deleteWorkspaceProject: (projectId: string) =>
    adminFetch<{ ok: boolean; hard_deleted: boolean; project_id: string }>(
      `/workspace/projects/${encodeURIComponent(projectId)}`,
      { method: 'DELETE' }
    ),

  deactivateWorkspaceProject: (projectId: string) =>
    adminFetch<{ ok: boolean; project: WorkspaceProjectSummary }>(
      `/workspace/projects/${encodeURIComponent(projectId)}/deactivate`,
      { method: 'POST' }
    ),

  reactivateWorkspaceProject: (projectId: string) =>
    adminFetch<{ ok: boolean; project: WorkspaceProjectSummary }>(
      `/workspace/projects/${encodeURIComponent(projectId)}/reactivate`,
      { method: 'POST' }
    ),

  listWorkspaceProjectAgents: (projectId: string) =>
    adminFetch<{
      project_id: string;
      agents: {
        project_id: string;
        worker_uid: string;
        worker_id: string;
        display_name: string;
        role: string;
        sort_order: string;
      }[];
    }>(`/workspace/projects/${encodeURIComponent(projectId)}/agents`).then((r) => r.agents),

  assignWorkspaceProjectAgent: (
    projectId: string,
    body: { worker_id: string; role?: string; sort_order?: number }
  ) =>
    adminFetch<{ ok: boolean; project_id: string; agent: { worker_id: string; role: string } }>(
      `/workspace/projects/${encodeURIComponent(projectId)}/agents`,
      {
        method: 'POST',
        body: JSON.stringify(body),
      }
    ),

  removeWorkspaceProjectAgent: (projectId: string, workerId: string) =>
    adminFetch<{ ok: boolean; project_id: string; worker_id: string }>(
      `/workspace/projects/${encodeURIComponent(projectId)}/agents/${encodeURIComponent(workerId)}`,
      { method: 'DELETE' }
    ),

  listKnowledgeSources: (params: { project_id?: string; worker_uid?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.project_id) qs.set('project_id', params.project_id);
    if (params.worker_uid) qs.set('worker_uid', params.worker_uid);
    return adminFetch<{ sources: KnowledgeSource[] }>(`/knowledge/sources${qs.toString() ? `?${qs}` : ''}`).then(
      (r) => r.sources
    );
  },

  getKnowledgeConfig: () =>
    adminFetch<{
      allowed_roots: { path: string; label: string; exists: boolean }[];
      output_roots: { path: string; label: string; exists: boolean }[];
      auto_sync: boolean;
      auto_sync_poll_sec: number;
    }>('/knowledge/config'),

  browseKnowledgeFolders: (path = '') => {
    const qs = path.trim() ? `?path=${encodeURIComponent(path.trim())}` : '';
    return adminFetch<KnowledgeBrowseResponse>(`/knowledge/browse${qs}`);
  },

  getKnowledgeSyncJobStatus: (jobId: string) =>
    adminFetch<{
      job_id: string;
      status: string;
      detail?: string;
      updated_at?: number;
      progress?: {
        files_total?: number;
        files_done?: number;
        chunks_done?: number;
        phase?: string;
        current_file?: string;
      };
    }>(`/knowledge/jobs/${encodeURIComponent(jobId)}`),

  getKnowledgeSourceIndexingProgress: (sourceId: string) =>
    adminFetch<{
      active: boolean;
      source_id: string;
      job_id?: string | null;
      job_status?: string | null;
      progress?: {
        files_total?: number;
        files_done?: number;
        chunks_done?: number;
        phase?: string;
        current_file?: string;
      };
      file_count?: number;
      document_count?: number;
      chunk_count?: number;
      error_message?: string | null;
    }>(`/knowledge/sources/${encodeURIComponent(sourceId)}/indexing-progress`),

  createKnowledgeSource: (body: {
    source_uri: string;
    display_name?: string;
    source_kind?: string;
    project_id?: string;
    worker_uid?: string;
    metadata?: Record<string, unknown>;
    ingest?: boolean;
    compute_embeddings?: boolean;
  }) =>
    adminFetch<{
      ok: boolean;
      source_id: string;
      status?: string;
      task_ids: string[];
      sync_job_id?: string;
      message?: string;
      documents: number;
      chunks: number;
      skipped_hidden?: number;
      skipped_unsupported?: number;
    }>('/knowledge/sources', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  previewKnowledgeFolder: (source_uri: string) =>
    adminFetch<{
      ok: boolean;
      source_uri: string;
      file_count: number;
      skipped_hidden: number;
      skipped_secret: number;
      skipped_unsupported: number;
      sample_paths: string[];
    }>('/knowledge/sources/preview', {
      method: 'POST',
      body: JSON.stringify({ source_uri }),
    }),

  syncKnowledgeSource: (
    sourceId: string,
    body: { compute_embeddings?: boolean } = {}
  ) =>
    adminFetch<{
      ok: boolean;
      accepted?: boolean;
      source_id: string;
      status?: string;
      task_ids: string[];
      sync_job_id?: string;
      message?: string;
      scanned?: number;
      upserted?: number;
      skipped?: number;
      removed?: number;
      chunks?: number;
    }>(`/knowledge/sources/${encodeURIComponent(sourceId)}/sync`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  uploadKnowledgeFiles: (body: {
    files: File[];
    display_name?: string;
    project_id?: string;
    worker_uid?: string;
    compute_embeddings?: boolean;
  }) => {
    const form = new FormData();
    form.set('display_name', body.display_name || '');
    form.set('project_id', body.project_id || '');
    form.set('worker_uid', body.worker_uid || '');
    form.set('compute_embeddings', body.compute_embeddings === false ? 'false' : 'true');
    for (const file of body.files) {
      const relativePath = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
      form.append('files', file, relativePath);
    }
    return adminFormFetch<{
      ok: boolean;
      accepted?: boolean;
      source_id: string;
      status?: string;
      task_ids: string[];
      sync_job_id?: string;
      message?: string;
      documents: number;
      chunks: number;
    }>('/knowledge/uploads', form);
  },

  deleteKnowledgeSource: (sourceId: string) =>
    adminFetch<{ ok: boolean; source_id: string; task_id: string }>(
      `/knowledge/sources/${encodeURIComponent(sourceId)}`,
      { method: 'DELETE' }
    ),

  searchKnowledge: (body: {
    query: string;
    project_id?: string;
    worker_uid?: string;
    source_id?: string;
    limit?: number;
  }) =>
    adminFetch<{ results: KnowledgeSearchResult[]; count: number }>('/knowledge/search', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  listReportInstances: (params?: { project_id?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.project_id) qs.set('project_id', params.project_id);
    if (params?.limit) qs.set('limit', String(params.limit));
    const query = qs.toString();
    return adminFetch<{ instances: ReportInstanceSummary[]; count: number }>(
      `/report-instances${query ? `?${query}` : ''}`
    );
  },

  getReportInstance: (instanceId: string) =>
    adminFetch<ReportInstanceDetail>(`/report-instances/${encodeURIComponent(instanceId)}`),

  createManagedWorkspaceDraft: (body: { prompt: string }) =>
    adminFetch<ManagedWorkspaceDraft>('/workspace/orchestrator/draft', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  confirmManagedWorkspaceDraft: (draft: ManagedWorkspaceDraft) =>
    adminFetch<{
      ok: boolean;
      task_id: string;
      project: {
        project_id: string;
        tenant_id: string;
        owner_email: string;
        name: string;
        description: string;
        status: string;
        visibility: string;
      };
      created: { workers: TemplateSummary[] };
    }>('/workspace/orchestrator/confirm', {
      method: 'POST',
      body: JSON.stringify({ draft }),
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
    const res = await fetch('/api/admin/playground/chat', {
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
      throw err;
    }
    if (options?.signal?.aborted) return full;
    return full;
  },
};
