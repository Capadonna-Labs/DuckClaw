export type AdminRole = 'admin' | 'viewer';

export interface AdminUser {
  id: string;
  email: string;
  nombre: string;
  rol: AdminRole;
  initials: string;
}

export interface TemplateSummary {
  id: string;
  name?: string;
  schema_name?: string;
  temperature?: number;
  topology?: string;
  load_error?: string;
}

export interface TemplateDetail {
  id: string;
  files: { path: string; size: number }[];
  contents: Record<string, string>;
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

export interface WhitelistUser {
  user_id: string;
  username: string;
  role: string;
}

export interface FlyCommandEntry {
  cmd: string;
  description: string;
}
