import { describe, expect, it } from 'vitest';
import {
  buildDraftManifestYaml,
  parseDraftCompositionFromManifest,
  type DraftComposition,
} from './draftManifestYaml';
import { parseManifestSkills } from './manifestSkillsEdit';
import { parseManifestQuick } from './manifestQuickEdit';

const BASE: DraftComposition = {
  tool_profile: 'general',
  skills: ['google_trends'],
  browser_sandbox: true,
  web_search: false,
};

describe('draftManifestYaml', () => {
  it('builds manifest with profile, toggles and optional skills', () => {
    const yaml = buildDraftManifestYaml(BASE);
    const quick = parseManifestQuick(yaml);
    expect(quick.toolProfile).toBe('general');
    expect(quick.browserSandbox).toBe(true);
    expect(quick.webSearch).toBe(false);
    expect(parseManifestSkills(yaml).optionalSkillNames).toEqual(['google_trends']);
  });

  it('round-trips composition from manifest yaml', () => {
    const yaml = buildDraftManifestYaml(BASE);
    const roundTrip = parseDraftCompositionFromManifest(yaml, {
      tool_profile: 'minimal',
      skills: [],
      browser_sandbox: false,
      web_search: false,
    });
    expect(roundTrip).toEqual(BASE);
  });

  it('preserves rag profile and extra skills', () => {
    const yaml = buildDraftManifestYaml({
      ...BASE,
      tool_profile: 'rag_only',
      skills: ['reddit', 'research'],
    });
    const parsed = parseDraftCompositionFromManifest(yaml, BASE);
    expect(parsed.tool_profile).toBe('rag_only');
    expect(parsed.skills).toContain('reddit');
  });
});
