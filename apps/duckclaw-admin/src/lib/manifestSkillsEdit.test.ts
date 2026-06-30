import assert from 'node:assert/strict';
import {
  applyManifestSkills,
  applyReportsBundle,
  parseManifestSkills,
  reportsBundleFullySelected,
  toggleOptionalSkill,
} from './manifestSkillsEdit';

const SIMPLE = `id: ui-designer
name: UI Designer
tool_profile: general
skills:
  - google_trends
`;

const RESEARCH_BLOCK = `id: researcher
skills:
  - research:
      tavily_enabled: true
      search_depth: advanced
      max_results: 8
`;

const parsedSimple = parseManifestSkills(SIMPLE);
assert.deepEqual(parsedSimple.optionalSkillNames, ['google_trends']);
assert.equal(parsedSimple.skillNames.length, 1);

const parsedResearch = parseManifestSkills(RESEARCH_BLOCK);
assert.equal(parsedResearch.optionalSkillNames[0], 'research');
assert.deepEqual(parsedResearch.bindings.research, {
  tavily_enabled: true,
  search_depth: 'advanced',
  max_results: 8,
});

const toggledOn = toggleOptionalSkill(SIMPLE, 'reddit', true);
assert.ok(parseManifestSkills(toggledOn).optionalSkillNames.includes('reddit'));

const toggledOff = toggleOptionalSkill(toggledOn, 'google_trends', false);
assert.ok(!parseManifestSkills(toggledOff).optionalSkillNames.includes('google_trends'));

const withResearch = applyManifestSkills(SIMPLE, ['google_trends', 'research']);
const researchParsed = parseManifestSkills(withResearch);
assert.ok(researchParsed.optionalSkillNames.includes('research'));
assert.equal(researchParsed.bindings.research?.tavily_enabled, true);

const bundleOn = applyReportsBundle(SIMPLE, true);
assert.equal(reportsBundleFullySelected(bundleOn), true);
const bundleOff = applyReportsBundle(bundleOn, false);
assert.equal(reportsBundleFullySelected(bundleOff), false);

console.log('manifestSkillsEdit.test.ts: ok');
