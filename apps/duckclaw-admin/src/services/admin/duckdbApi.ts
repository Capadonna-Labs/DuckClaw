import { adminFetch } from './http';

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

export interface PgqBootstrapResult {
  ok: boolean;
  vault_path: string;
  pgq_available: boolean;
  tables_created: string[];
}

export interface PgqRebuildResult {
  ok: boolean;
  vault_path: string;
  html_path: string;
  cache_key: string;
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

export const duckdbApi = {
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
  bootstrapDuckdbPgq: (vaultPath?: string) =>
    adminFetch<PgqBootstrapResult>('/duckdb/pgq/bootstrap', {
      method: 'POST',
      body: JSON.stringify({ vault_path: vaultPath }),
    }),
  rebuildDuckdbPgqGraph: (vaultPath?: string) =>
    adminFetch<PgqRebuildResult>('/duckdb/pgq/rebuild', {
      method: 'POST',
      body: JSON.stringify({ vault_path: vaultPath }),
    }),
  pgqGraphHtmlUrl: (vaultPath: string, cacheToken?: number) => {
    const q = new URLSearchParams({ vault_path: vaultPath });
    q.set('_t', String(cacheToken ?? Date.now()));
    return `/api/admin/duckdb/pgq-graph/html?${q}`;
  },
  searchDuckdbVectorMemory: (body: { query?: string; limit?: number; vault_path?: string }) =>
    adminFetch<VectorSearchResult>('/duckdb/vector-search', {
      method: 'POST',
      body: JSON.stringify(body),
    }),
};
