/** Resuelve cómo «instalar» una skill sugerida en el wizard. */

import { FALLBACK_PLATFORM_CATEGORIES } from '@/lib/skillCategories';
import { normalizeSkillId } from '@/lib/skillCategories';
import { defaultImplementationRef } from '@/components/skills/useSkillsCatalog';

export type SuggestedSkillInstallKind = 'activated' | 'platform' | 'catalog' | 'custom';

export type SuggestedSkillRow = {
  name: string;
  reason: string;
  available: boolean;
};

export function collectPlatformSkillIds(extraIds: string[] = []): Set<string> {
  const ids = new Set<string>();
  for (const category of FALLBACK_PLATFORM_CATEGORIES) {
    for (const skill of category.skills) {
      ids.add(normalizeSkillId(skill.id));
    }
  }
  for (const id of extraIds) {
    const normalized = normalizeSkillId(id);
    if (normalized) ids.add(normalized);
  }
  return ids;
}

export function resolveSuggestedSkillInstall(params: {
  skill: SuggestedSkillRow;
  draftSkills: string[];
  platformSkillIds: Set<string>;
  catalogSkillNames: Set<string>;
}): SuggestedSkillInstallKind {
  const id = normalizeSkillId(params.skill.name);
  if (!id) return 'custom';
  const draftSet = new Set(params.draftSkills.map(normalizeSkillId));
  if (draftSet.has(id)) return 'activated';
  if (params.catalogSkillNames.has(id) || params.skill.available) return 'catalog';
  if (params.platformSkillIds.has(id)) return 'platform';
  return 'custom';
}

export function catalogSkillNamesFromLists(global: { id: string }[], local: { id: string }[]): Set<string> {
  const names = new Set<string>();
  for (const skill of [...global, ...local]) {
    const id = normalizeSkillId(skill.id);
    if (id) names.add(id);
  }
  return names;
}

export function buildCatalogSkillCreateBody(skill: SuggestedSkillRow) {
  const name = normalizeSkillId(skill.name);
  return {
    name,
    description: skill.reason.trim().slice(0, 1024) || `Skill sugerida: ${name}`,
    skill_type: 'python',
    implementation_ref: defaultImplementationRef(name),
    visibility: 'private' as const,
  };
}

export function mergeSkillIntoDraft(skills: string[], skillName: string): string[] {
  const id = normalizeSkillId(skillName);
  if (!id) return skills;
  const merged = new Set(skills.map(normalizeSkillId).filter(Boolean));
  merged.add(id);
  return Array.from(merged);
}
