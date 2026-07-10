/** Parse and apply optional skills in manifest.yaml (preserves dict-style bindings). */

import yaml from 'js-yaml';
import { FALLBACK_BASELINE_PROFILES, isBaselineSkill, normalizeSkillId } from './skillCategories';

function isFrameworkBaseline(skillId: string): boolean {
  return isBaselineSkill(skillId, FALLBACK_BASELINE_PROFILES);
}

export type ManifestSkillBindings = Record<string, Record<string, unknown> | null>;

export type ParsedManifestSkills = {
  skillNames: string[];
  optionalSkillNames: string[];
  bindings: ManifestSkillBindings;
};

const DEFAULT_RESEARCH_CONFIG: Record<string, unknown> = {
  tavily_enabled: true,
  search_depth: 'basic',
};

const DEFAULT_COMFYUI_CONFIG: Record<string, unknown> = {
  enabled: true,
};

const DEFAULT_HIGGSFIELD_CONFIG: Record<string, unknown> = {
  enabled: true,
  token_env: 'HIGGSFIELD_API_KEY',
};

const DEFAULT_FAL_CONFIG: Record<string, unknown> = {
  enabled: true,
  token_env: 'FAL_KEY',
};

const DEFAULT_GITHUB_CONFIG: Record<string, unknown> = {
  enabled: true,
  token_env: 'GITHUB_TOKEN',
  mcp_read_only: true,
  hitl_destructive: true,
};

function addSkillBinding(
  bindings: ManifestSkillBindings,
  skillNames: string[],
  name: string,
  config: Record<string, unknown> | null
) {
  const normalized = normalizeSkillId(name);
  if (!normalized) return;
  if (!skillNames.includes(normalized)) {
    skillNames.push(normalized);
  }
  if (config !== null) {
    bindings[normalized] = config;
  }
}

function parseSkillItem(
  item: unknown,
  skillNames: string[],
  bindings: ManifestSkillBindings
) {
  if (typeof item === 'string') {
    addSkillBinding(bindings, skillNames, item, null);
    return;
  }
  if (!item || typeof item !== 'object' || Array.isArray(item)) {
    return;
  }
  const record = item as Record<string, unknown>;
  const rawName = record.name;
  if (typeof rawName === 'string') {
    const rawConfig = record.config;
    const config =
      rawConfig && typeof rawConfig === 'object' && !Array.isArray(rawConfig)
        ? (rawConfig as Record<string, unknown>)
        : Object.fromEntries(
            Object.entries(record).filter(([key]) => key !== 'name' && key !== 'id')
          );
    addSkillBinding(
      bindings,
      skillNames,
      rawName,
      Object.keys(config).length > 0 ? config : null
    );
    return;
  }
  const entries = Object.entries(record);
  if (entries.length === 1) {
    const [name, config] = entries[0];
    const parsedConfig =
      config && typeof config === 'object' && !Array.isArray(config)
        ? (config as Record<string, unknown>)
        : null;
    addSkillBinding(bindings, skillNames, name, parsedConfig);
  }
}

export function parseManifestSkills(yamlText: string): ParsedManifestSkills {
  if (!yamlText.trim()) {
    return { skillNames: [], optionalSkillNames: [], bindings: {} };
  }
  let doc: unknown;
  try {
    doc = yaml.load(yamlText);
  } catch {
    return { skillNames: [], optionalSkillNames: [], bindings: {} };
  }
  if (!doc || typeof doc !== 'object' || Array.isArray(doc)) {
    return { skillNames: [], optionalSkillNames: [], bindings: {} };
  }
  const skillsRaw = (doc as Record<string, unknown>).skills;
  let skillsList: unknown[] = [];
  if (typeof skillsRaw === 'string') {
    skillsList = skillsRaw
      .split(',')
      .map((part) => part.trim())
      .filter(Boolean);
  } else if (Array.isArray(skillsRaw)) {
    skillsList = skillsRaw;
  }
  const skillNames: string[] = [];
  const bindings: ManifestSkillBindings = {};
  for (const item of skillsList) {
    parseSkillItem(item, skillNames, bindings);
  }
  const optionalSkillNames = skillNames.filter((name) => !isFrameworkBaseline(name));
  return { skillNames, optionalSkillNames, bindings };
}

function defaultConfigForSkill(skillId: string): Record<string, unknown> | null {
  const normalized = normalizeSkillId(skillId);
  if (normalized === 'research') return { ...DEFAULT_RESEARCH_CONFIG };
  if (normalized === 'comfyui') return { ...DEFAULT_COMFYUI_CONFIG };
  if (normalized === 'higgsfield') return { ...DEFAULT_HIGGSFIELD_CONFIG };
  if (normalized === 'fal') return { ...DEFAULT_FAL_CONFIG };
  if (normalized === 'github') return { ...DEFAULT_GITHUB_CONFIG };
  return null;
}

function skillEntryForYaml(skillId: string, bindings: ManifestSkillBindings): unknown {
  const normalized = normalizeSkillId(skillId);
  const config = bindings[normalized] ?? defaultConfigForSkill(normalized);
  if (config && Object.keys(config).length > 0) {
    return { [normalized]: config };
  }
  return normalized;
}

export function applyManifestSkills(
  yamlText: string,
  selectedOptional: string[],
  existingBindings?: ManifestSkillBindings
): string {
  const parsed = parseManifestSkills(yamlText);
  const bindings = { ...parsed.bindings, ...(existingBindings ?? {}) };
  const selected = Array.from(
    new Set(
      selectedOptional.map(normalizeSkillId).filter((id) => id && !isFrameworkBaseline(id))
    )
  );

  const baselineNames = parsed.skillNames.filter((name) => isFrameworkBaseline(name));
  const baselineOrdered = Array.from(new Set(baselineNames.map(normalizeSkillId)));

  let doc: Record<string, unknown>;
  try {
    const loaded = yaml.load(yamlText);
    doc =
      loaded && typeof loaded === 'object' && !Array.isArray(loaded)
        ? { ...(loaded as Record<string, unknown>) }
        : {};
  } catch {
    doc = {};
  }

  const optionalEntries = selected.map((skillId) => skillEntryForYaml(skillId, bindings));
  const baselineEntries = baselineOrdered.map((skillId) => skillEntryForYaml(skillId, bindings));
  doc.skills = [...baselineEntries, ...optionalEntries];
  return `${yaml.dump(doc, { lineWidth: -1, noRefs: true, sortKeys: false }).trimEnd()}\n`;
}

export function toggleOptionalSkill(
  yamlText: string,
  skillId: string,
  enabled: boolean
): string {
  const parsed = parseManifestSkills(yamlText);
  const normalized = normalizeSkillId(skillId);
  const next = new Set(parsed.optionalSkillNames);
  if (enabled) {
    next.add(normalized);
  } else {
    next.delete(normalized);
  }
  return applyManifestSkills(yamlText, Array.from(next), parsed.bindings);
}

export function applyReportsBundle(yamlText: string, enabled: boolean): string {
  const parsed = parseManifestSkills(yamlText);
  const reportSkills = [
    'publish_custom_report',
    'update_custom_report_title',
    'read_llm_usage_summary',
  ];
  const next = new Set(parsed.optionalSkillNames);
  for (const skill of reportSkills) {
    if (enabled) {
      next.add(skill);
    } else {
      next.delete(skill);
    }
  }
  return applyManifestSkills(yamlText, Array.from(next), parsed.bindings);
}

export function reportsBundleFullySelected(yamlText: string): boolean {
  const parsed = parseManifestSkills(yamlText);
  const selected = new Set(parsed.optionalSkillNames);
  return (
    selected.has('publish_custom_report') &&
    selected.has('update_custom_report_title') &&
    selected.has('read_llm_usage_summary')
  );
}
