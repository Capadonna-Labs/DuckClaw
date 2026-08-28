import type { KnowledgeBrowseResponse } from './knowledgeApi';
import { adminFetch, adminFormFetch } from './http';

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

export interface ReportTemplateSummary {
  template_id: string;
  tenant_id: string;
  owner_email: string;
  name: string;
  description: string;
  template_uri: string;
  section_schema: Array<{ id: string; label?: string; required?: boolean }>;
  analyzer_mode: string;
  visibility: string;
}

export interface ProductivityArtifact {
  artifact_id: string;
  lane: 'storage' | 'vault' | 'report' | string;
  title: string;
  filename: string;
  uri: string;
  source_kind: string;
  source_ref: string;
  mime: string;
  byte_size: number;
  updated_at: string;
  progress_percent?: number;
}

export const reportsApi = {
  listReportInstances: (params?: { project_id?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.project_id) qs.set('project_id', params.project_id);
    if (params?.limit) qs.set('limit', String(params.limit));
    const query = qs.toString();
    return adminFetch<{ instances: ReportInstanceSummary[]; count: number }>(
      `/report-instances${query ? `?${query}` : ''}`
    );
  },

  listReportTemplates: (params?: { limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.limit) qs.set('limit', String(params.limit));
    const query = qs.toString();
    return adminFetch<{ templates: ReportTemplateSummary[]; count: number }>(
      `/report-templates${query ? `?${query}` : ''}`
    );
  },

  registerReportTemplate: (body: {
    template_docx_path: string;
    name?: string;
    description?: string;
    visibility?: string;
    template_id?: string;
  }) =>
    adminFetch<{
      ok: boolean;
      task_id: string;
      template_id: string;
      name: string;
      section_count: number;
      sections: Array<{ id: string; label?: string }>;
      analyzer_mode?: string;
    }>('/report-templates/register', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  createReportInstance: (body: {
    template_id: string;
    title: string;
    project_id?: string;
  }) =>
    adminFetch<{
      ok: boolean;
      task_id: string;
      instance_id: string;
      template_id: string;
      title: string;
      status: string;
    }>('/report-instances', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  getReportInstance: (instanceId: string) =>
    adminFetch<ReportInstanceDetail>(`/report-instances/${encodeURIComponent(instanceId)}`),

  deleteReportInstance: (instanceId: string) =>
    adminFetch<{ ok: boolean; task_id: string; instance_id: string; status: string }>(
      `/report-instances/${encodeURIComponent(instanceId)}`,
      { method: 'DELETE' }
    ),

  listProductivityArtifacts: (params?: { lane?: string; limit?: number }) => {
    const qs = new URLSearchParams();
    if (params?.lane) qs.set('lane', params.lane);
    if (params?.limit) qs.set('limit', String(params.limit));
    const query = qs.toString();
    return adminFetch<{ artifacts: ProductivityArtifact[]; count: number }>(
      `/productivity/artifacts${query ? `?${query}` : ''}`
    );
  },

  deleteProductivityArtifact: (artifactId: string) =>
    adminFetch<{ ok: boolean; task_id: string; artifact_id: string; lane: string }>(
      `/productivity/artifacts/${encodeURIComponent(artifactId)}`,
      { method: 'DELETE' }
    ),

  promoteProductivityArtifactToVault: (
    artifactId: string,
    body?: { relative_dir?: string; remove_from_storage?: boolean }
  ) =>
    adminFetch<{
      ok: boolean;
      source_artifact_id: string;
      vault_artifact_id: string;
      vault_uri: string;
      relative_path: string;
      filename: string;
      removed_from_storage: boolean;
    }>(`/productivity/artifacts/${encodeURIComponent(artifactId)}/promote-to-vault`, {
      method: 'POST',
      body: JSON.stringify(body || {}),
    }),

  browseProductivityVault: (path = '', files = '*') => {
    const qs = new URLSearchParams();
    if (path.trim()) qs.set('path', path.trim());
    if (files) qs.set('files', files);
    const query = qs.toString();
    return adminFetch<KnowledgeBrowseResponse>(
      `/productivity/vault/browse${query ? `?${query}` : ''}`
    );
  },

  indexProductivityVaultPath: (body: { path: string; title?: string }) =>
    adminFetch<{
      ok: boolean;
      artifact_id: string;
      lane: string;
      title: string;
      uri: string;
    }>('/productivity/vault/index', {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  deleteReportTemplate: (templateId: string) =>
    adminFetch<{ ok: boolean; task_id: string; template_id: string; status: string }>(
      `/report-templates/${encodeURIComponent(templateId)}`,
      { method: 'DELETE' }
    ),

  uploadCustomReportHtml: (
    reportId: string,
    body: { vault: string; file: File; title?: string }
  ) => {
    const form = new FormData();
    form.append('file', body.file);
    form.append('vault', body.vault.trim());
    if (body.title?.trim()) form.append('title', body.title.trim());
    return adminFormFetch<{ status: string; report_id: string; message?: string }>(
      `/reports/${encodeURIComponent(reportId)}/upload`,
      form
    );
  },
};
