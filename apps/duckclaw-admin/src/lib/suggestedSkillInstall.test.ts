import { describe, expect, it } from 'vitest';
import {
  buildCatalogSkillCreateBody,
  catalogSkillNamesFromLists,
  collectPlatformSkillIds,
  mergeSkillIntoDraft,
  resolveSuggestedSkillInstall,
} from './suggestedSkillInstall';

describe('suggestedSkillInstall', () => {
  it('detecta skill de plataforma no marcada available', () => {
    const platformIds = collectPlatformSkillIds(['reddit']);
    expect(
      resolveSuggestedSkillInstall({
        skill: { name: 'reddit', reason: 'Para foros', available: false },
        draftSkills: [],
        platformSkillIds: platformIds,
        catalogSkillNames: new Set(),
      })
    ).toBe('platform');
  });

  it('marca activada si ya está en draft.skills', () => {
    expect(
      resolveSuggestedSkillInstall({
        skill: { name: 'research', reason: 'Buscar', available: true },
        draftSkills: ['research'],
        platformSkillIds: collectPlatformSkillIds(),
        catalogSkillNames: new Set(['research']),
      })
    ).toBe('activated');
  });

  it('mergeSkillIntoDraft deduplica', () => {
    expect(mergeSkillIntoDraft(['reddit', 'web_search'], 'Reddit')).toEqual(['reddit', 'web_search']);
  });

  it('buildCatalogSkillCreateBody usa implementation_ref por defecto', () => {
    const body = buildCatalogSkillCreateBody({
      name: 'mi_skill',
      reason: 'Custom',
      available: false,
    });
    expect(body.implementation_ref).toBe('db://skills/mi_skill.py');
    expect(body.visibility).toBe('private');
  });

  it('catalogSkillNamesFromLists normaliza ids', () => {
    const names = catalogSkillNamesFromLists([{ id: 'Reddit' }], [{ id: 'local_one' }]);
    expect(names.has('reddit')).toBe(true);
    expect(names.has('local_one')).toBe(true);
  });
});
