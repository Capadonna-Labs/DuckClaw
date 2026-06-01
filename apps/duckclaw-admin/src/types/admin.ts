export type AdminRole = 'admin' | 'user' | 'viewer';

export interface AdminUser {
  id: string;
  email: string;
  nombre: string;
  rol: AdminRole;
  initials: string;
}

export interface TemplateSummary {
  id: string;
  worker_uid?: string;
  name?: string;
  description?: string;
  description_source?: string;
  source?: string;
  visibility?: string;
  source_template_id?: string;
  schema_name?: string;
  temperature?: number;
  topology?: string;
  load_error?: string;
}

export interface TemplateDetail {
  id: string;
  source?: 'catalog' | 'filesystem' | string;
  read_only?: boolean;
  display_name?: string;
  worker_uid?: string;
  version?: number;
  files: { path: string; size: number }[];
  contents: Record<string, string>;
  contexts?: {
    context_id: string;
    title: string;
    content_md: string;
    sort_order: string;
  }[];
}

export interface VaultOption {
  scope: string;
  vault_id: string;
  path: string;
  label: string;
}

export interface VaultBinding {
  scope: string;
  vault_id?: string;
  path?: string;
}

export interface EnvConfigResponse {
  path: string;
  values: Record<string, string>;
}

export interface RuntimeConfigRow {
  key: string;
  value: string;
}

export interface AdminHealth {
  status: string;
  workers_count: number;
  workers: string[];
  redis: boolean;
  templates_dir: string;
  api_revision?: number;
  features?: { catalog?: boolean; ops?: boolean; projects?: boolean };
}

export interface ConsoleUser {
  email: string;
  nombre: string;
  rol: AdminRole;
  initials: string;
  active: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface SharedDbGrant {
  user_id: string;
  resource_key: string;
  created_at?: string;
}

export interface WhitelistUser {
  user_id: string;
  username: string;
  role: string;
}

export interface FlyCommandEntry {
  cmd: string;
  description: string;
}

export interface OverviewActivityRow {
  worker_id: string;
  success_count: number;
  failed_count: number;
}

export interface OverviewLatencyRow {
  hour: string;
  avg_latency: number;
}

export interface OverviewMetrics {
  activity: OverviewActivityRow[];
  latency: OverviewLatencyRow[];
  db_path?: string;
}
