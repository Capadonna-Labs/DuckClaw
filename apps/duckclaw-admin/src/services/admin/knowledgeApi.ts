import { adminFetch, adminFormFetch, coalesceAdminGet } from './http';

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
  kind: 'root' | 'directory' | 'file';
  exists: boolean;
  selectable: boolean;
};

export type KnowledgeBrowseResponse = {
  path: string;
  parent_path: string | null;
  roots_mode: boolean;
  entries: KnowledgeBrowseEntry[];
  include_suffixes?: string[];
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

export const knowledgeApi = {
  listKnowledgeSources: (params: { project_id?: string; worker_uid?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.project_id) qs.set('project_id', params.project_id);
    if (params.worker_uid) qs.set('worker_uid', params.worker_uid);
    const path = `/knowledge/sources${qs.toString() ? `?${qs}` : ''}`;
    return coalesceAdminGet(`GET:${path}`, () =>
      adminFetch<{ sources: KnowledgeSource[] }>(path)
    ).then((r) => r.sources);
  },

  getKnowledgeConfig: () =>
    adminFetch<{
      allowed_roots: { path: string; label: string; exists: boolean }[];
      output_roots: { path: string; label: string; exists: boolean }[];
      auto_sync: boolean;
      auto_sync_poll_sec: number;
    }>('/knowledge/config'),

  browseKnowledgeFolders: (path = '', opts?: { files?: string }) => {
    const qs = new URLSearchParams();
    if (path.trim()) qs.set('path', path.trim());
    if (opts?.files?.trim()) qs.set('files', opts.files.trim());
    const query = qs.toString();
    return adminFetch<KnowledgeBrowseResponse>(`/knowledge/browse${query ? `?${query}` : ''}`);
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
    })
};
