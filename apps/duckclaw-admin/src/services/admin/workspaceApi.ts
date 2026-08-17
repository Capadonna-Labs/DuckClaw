import type { TemplateSummary } from '@/types/admin';

import { adminFetch, adminFormFetch } from './http';

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

function listWorkspaceProjectsPage(params?: WorkspaceProjectsQuery) {
  return adminFetch<WorkspaceProjectsPage>(`/workspace/projects${workspaceProjectsQueryString(params)}`);
}

export const workspaceApi = {
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
  updateWorkspaceProject: (
    projectId: string,
    body: { name?: string; description?: string; visibility?: string }
  ) =>
    adminFetch<{ ok: boolean; task_id?: string; project: WorkspaceProjectSummary }>(
      `/workspace/projects/${encodeURIComponent(projectId)}`,
      {
        method: 'PATCH',
        body: JSON.stringify(body),
      }
    ),
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
  confirmManagedWorkspaceDraftWithImport: (
    draft: ManagedWorkspaceDraft,
    packages: {
      file: File;
      role?: string;
      confirm_high_risk?: boolean;
      worker_id_override?: string;
    }[]
  ) => {
    const form = new FormData();
    form.append('draft_json', JSON.stringify(draft));
    const mapping = packages.map((pkg, file_index) => ({
      file_index,
      role: pkg.role || 'member',
      confirm_high_risk: Boolean(pkg.confirm_high_risk),
      worker_id_override: pkg.worker_id_override || undefined,
    }));
    form.append('mapping_json', JSON.stringify(mapping));
    for (const pkg of packages) {
      form.append('files', pkg.file);
    }
    return adminFormFetch<{
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
      spawn_import_count: number;
    }>('/workspace/orchestrator/confirm-with-import', form);
  },
};
