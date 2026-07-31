/** Skill category helpers for the worker tools dropdown (data from DuckDB via gateway). */

import type { SkillCatalogItem, SkillCategoryPayload } from '@/services/adminService';
import { parseManifestSkills } from './manifestSkillsEdit';
import type { ToolProfile } from './manifestQuickEdit';
import { parseManifestQuick } from './manifestQuickEdit';

export type SkillCategoryEntry = {
  id: string;
  label: string;
  hint?: string;
  baseline?: boolean;
};

export type SkillCategory = {
  id: string;
  title: string;
  description?: string;
  skills: SkillCategoryEntry[];
  readOnly?: boolean;
};

/** Fallback when gateway catalog is unavailable (matches framework_skill_categories_v1 seed). */
export const FALLBACK_PLATFORM_CATEGORIES: SkillCategory[] = [
  {
    id: 'web',
    title: 'Web e investigación',
    skills: [
      { id: 'research', label: 'research' },
      { id: 'google_trends', label: 'google_trends' },
      { id: 'reddit', label: 'reddit' },
      { id: 'openweather', label: 'openweather' },
    ],
  },
  {
    id: 'reports_html',
    title: 'Reportes HTML',
    skills: [
      { id: 'publish_custom_report', label: 'publish_custom_report' },
      { id: 'update_custom_report_title', label: 'update_custom_report_title' },
      { id: 'read_llm_usage_summary', label: 'read_llm_usage_summary' },
    ],
  },
  {
    id: 'visual',
    title: 'Visual y media',
    description: 'Generación de imágenes, video y artefactos visuales.',
    skills: [
      { id: 'comfyui', label: 'comfyui', hint: 'ComfyUI (config avanzada en YAML)' },
      { id: 'fal', label: 'fal.ai', hint: 'Generación de imágenes con fal.ai (Flux, etc.)' },
      { id: 'higgsfield', label: 'Higgsfield', hint: 'Video e imágenes con Higgsfield API' },
    ],
  },
  {
    id: 'mcp',
    title: 'MCP',
    skills: [
      {
        id: 'github',
        label: 'GitHub',
        hint: 'GitHub MCP oficial (Docker + GITHUB_TOKEN)',
      },
      {
        id: 'youtube_transcript',
        label: 'YouTube Transcript',
        hint: 'Transcripciones YouTube vía uvx (read-only)',
      },
    ],
  },
];

export const FALLBACK_BASELINE_PROFILES: Record<ToolProfile, string[]> = {
  general: [
    'get_current_time',
    'read_sql',
    'inspect_schema',
    'list_project_knowledge',
    'read_project_knowledge',
    'search_project_knowledge',
    'write_output_document',
    'delete_output_document',
    'convert_document',
    'extract_document_text',
    'render_docx_template',
  ],
  minimal: ['get_current_time', 'read_sql'],
  rag_only: [
    'get_current_time',
    'list_project_knowledge',
    'read_project_knowledge',
    'search_project_knowledge',
    'write_output_document',
    'delete_output_document',
  ],
};

export const REPORTS_HTML_SKILLS = [
  'publish_custom_report',
  'update_custom_report_title',
  'read_llm_usage_summary',
] as const;

export function normalizeSkillId(skillId: string): string {
  return skillId.trim().toLowerCase().replace(/-/g, '_');
}

export function isBaselineSkill(
  skillId: string,
  baselineProfiles: Record<string, string[]>
): boolean {
  const normalized = normalizeSkillId(skillId);
  for (const skills of Object.values(baselineProfiles)) {
    if (skills.some((item) => normalizeSkillId(item) === normalized)) {
      return true;
    }
  }
  return false;
}

function mapPayloadCategory(category: SkillCategoryPayload): SkillCategory {
  return {
    id: category.id,
    title: category.title,
    description: category.description ?? undefined,
    readOnly: false,
    skills: (category.skills ?? []).map((skill) => ({
      id: skill.id,
      label: skill.label || skill.id,
      hint: skill.hint ?? undefined,
    })),
  };
}

export function baselineCategoryForProfile(
  profile: ToolProfile,
  baselineProfiles: Record<string, string[]>
): SkillCategory {
  const skills = baselineProfiles[profile] ?? baselineProfiles.general ?? [];
  return {
    id: 'baseline',
    title: 'Plataforma (baseline)',
    description: 'Incluidas automáticamente según el perfil de herramientas.',
    readOnly: true,
    skills: skills.map((id) => ({ id, label: id, baseline: true })),
  };
}

function knownSkillIdsFromPacks(
  packs: SkillCategory[],
  baselineProfiles: Record<string, string[]>
): Set<string> {
  const ids = new Set<string>();
  for (const category of packs) {
    for (const skill of category.skills) {
      ids.add(normalizeSkillId(skill.id));
    }
  }
  for (const skills of Object.values(baselineProfiles)) {
    for (const skill of skills) {
      ids.add(normalizeSkillId(skill));
    }
  }
  return ids;
}

function customCatalogCategory(
  globalSkills: SkillCatalogItem[],
  localSkills: SkillCatalogItem[],
  workerId: string,
  knownIds: Set<string>
): SkillCategory | null {
  const wid = (workerId ?? '').trim();
  const entries: SkillCategoryEntry[] = [];
  for (const skill of globalSkills) {
    const id = normalizeSkillId(skill.id);
    if (!knownIds.has(id)) {
      entries.push({ id, label: skill.id, hint: skill.path });
    }
  }
  for (const skill of localSkills) {
    if (wid && skill.worker_id && skill.worker_id !== wid) continue;
    const id = normalizeSkillId(skill.id);
    if (!knownIds.has(id)) {
      entries.push({ id, label: skill.id, hint: skill.path });
    }
  }
  if (entries.length === 0) return null;
  const unique = new Map(entries.map((e) => [e.id, e]));
  return {
    id: 'custom',
    title: 'Personalizadas',
    description: 'Skills del catálogo global o locales del worker (admin_skills).',
    skills: Array.from(unique.values()).sort((a, b) => a.id.localeCompare(b.id)),
  };
}

function otherManifestCategory(
  manifestYaml: string,
  knownIds: Set<string>,
  baselineProfiles: Record<string, string[]>
): SkillCategory | null {
  const parsed = parseManifestSkills(manifestYaml);
  const others = parsed.optionalSkillNames
    .map(normalizeSkillId)
    .filter((id) => id && !knownIds.has(id) && !isBaselineSkill(id, baselineProfiles));
  const unique = Array.from(new Set(others)).sort();
  if (unique.length === 0) return null;
  return {
    id: 'other',
    title: 'Otras',
    description: 'Skills declaradas en el manifest sin categoría fija.',
    skills: unique.map((id) => ({ id, label: id })),
  };
}

/** Build categorized skill list for the tools dropdown. */
export function buildSkillCategories(
  manifestYaml: string,
  globalSkills: SkillCatalogItem[],
  localSkills: SkillCatalogItem[],
  workerId: string | undefined,
  platformCategories: SkillCategory[],
  baselineProfiles: Record<string, string[]>
): SkillCategory[] {
  const quick = parseManifestQuick(manifestYaml);
  const profiles =
    Object.keys(baselineProfiles).length > 0 ? baselineProfiles : FALLBACK_BASELINE_PROFILES;
  const staticPacks =
    platformCategories.length > 0 ? platformCategories : FALLBACK_PLATFORM_CATEGORIES;
  const knownIds = knownSkillIdsFromPacks(staticPacks, profiles);
  const baseline = baselineCategoryForProfile(quick.toolProfile, profiles);
  for (const skill of baseline.skills) {
    knownIds.add(normalizeSkillId(skill.id));
  }

  const categories: SkillCategory[] = [baseline, ...staticPacks];

  const custom = customCatalogCategory(globalSkills, localSkills, workerId ?? '', knownIds);
  if (custom) {
    for (const skill of custom.skills) {
      knownIds.add(normalizeSkillId(skill.id));
    }
    categories.push(custom);
  }

  const other = otherManifestCategory(manifestYaml, knownIds, profiles);
  if (other) {
    categories.push(other);
  }

  return categories;
}
