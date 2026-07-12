import type { IntegrationCatalogItem, IntegrationCatalogResponse } from '@/services/adminService';
import { normalizeSkillId } from '@/lib/skillCategories';

export type IntegrationGapPayload = {
  skill: string;
  integration_id: string;
  label: string;
  setting_key: string;
  env_fallback: string;
  configured: boolean;
  admin_href: string;
  message: string;
};

export type IntegrationGapView = {
  skill: string;
  integration: IntegrationCatalogItem;
};

/** Skills implied by draft composition (web_search → research en manifest). */
export function effectiveSkillIdsFromDraft(params: {
  skills: string[];
  web_search?: boolean;
}): string[] {
  const ids = params.skills.map(normalizeSkillId).filter(Boolean);
  if (params.web_search && !ids.includes('research')) {
    ids.push('research');
  }
  return ids;
}

export function missingIntegrationsForSkills(
  catalog: IntegrationCatalogResponse | null,
  skillIds: string[]
): IntegrationGapView[] {
  if (!catalog?.integrations?.length) return [];
  const active = new Set(skillIds.map(normalizeSkillId).filter(Boolean));
  const out: IntegrationGapView[] = [];
  const seen = new Set<string>();

  for (const integration of catalog.integrations) {
    if (integration.configured) continue;
    for (const skill of integration.related_skills) {
      const skillId = normalizeSkillId(skill);
      if (!skillId || !active.has(skillId)) continue;
      const key = `${integration.id}:${skillId}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ skill: skillId, integration });
    }
  }
  return out;
}

export function integrationGapViewsFromPayload(
  rows: IntegrationGapPayload[] | undefined
): IntegrationGapPayload[] {
  return (rows ?? []).filter((row) => !row.configured && row.message);
}
