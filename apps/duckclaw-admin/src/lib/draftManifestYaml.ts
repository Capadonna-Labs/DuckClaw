/** Bridge draft composition ↔ manifest YAML for WorkerSkillPickerPanel. */

import { applyManifestQuick, parseManifestQuick, type ToolProfile } from '@/lib/manifestQuickEdit';
import { applyManifestSkills, parseManifestSkills } from '@/lib/manifestSkillsEdit';

export type DraftComposition = {
  tool_profile: ToolProfile;
  skills: string[];
  browser_sandbox: boolean;
  web_search: boolean;
};

export function buildDraftManifestYaml(composition: DraftComposition): string {
  let yaml = `id: draft\nname: draft\ntool_profile: ${composition.tool_profile}\nskills: []\n`;
  yaml = applyManifestQuick(yaml, {
    toolProfile: composition.tool_profile,
    browserSandbox: composition.browser_sandbox,
    webSearch: composition.web_search,
    baselineOff: false,
    maxToolRounds: 10,
  });
  return applyManifestSkills(yaml, composition.skills, {});
}

export function parseDraftCompositionFromManifest(
  yaml: string,
  fallback: DraftComposition
): DraftComposition {
  try {
    const quick = parseManifestQuick(yaml);
    const parsed = parseManifestSkills(yaml);
    return {
      tool_profile: quick.toolProfile,
      browser_sandbox: quick.browserSandbox,
      web_search: quick.webSearch,
      skills: parsed.optionalSkillNames,
    };
  } catch {
    return fallback;
  }
}
