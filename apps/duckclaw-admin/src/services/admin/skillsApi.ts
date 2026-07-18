import { adminFetch } from './http';

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

export interface IndustryOption {
  id: string;
  name: string;
  path: string;
}

export const skillsApi = {
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
  getTopologiesCatalog: () =>
    adminFetch<{
      topologies: { id: string; label: string; description: string }[];
    }>('/catalog/topologies'),
};
