import { describe, expect, it } from 'vitest';
import {
  applyManifestQuick,
  parseManifestQuick,
  DEFAULT_MAX_TOOL_ROUNDS,
  MAX_TOOL_ROUNDS_CEILING,
} from '@/lib/manifestQuickEdit';

const base = `id: finanz-1
name: Finanz 1
tool_profile: general
skills: []
`;

describe('manifestQuickEdit max_tool_rounds', () => {
  it('roundtrips non-default slider values', () => {
    let yaml = base;
    for (const n of [15, 25, 1, 50, 12]) {
      yaml = applyManifestQuick(yaml, {
        ...parseManifestQuick(yaml),
        maxToolRounds: n,
      });
      expect(parseManifestQuick(yaml).maxToolRounds).toBe(n);
      expect(yaml).toMatch(/max_tool_rounds:\s*\d+/);
    }
  });

  it('omits agent_node when value is the default', () => {
    const withCustom = applyManifestQuick(base, {
      ...parseManifestQuick(base),
      maxToolRounds: 20,
    });
    const backToDefault = applyManifestQuick(withCustom, {
      ...parseManifestQuick(withCustom),
      maxToolRounds: DEFAULT_MAX_TOOL_ROUNDS,
    });
    expect(parseManifestQuick(backToDefault).maxToolRounds).toBe(DEFAULT_MAX_TOOL_ROUNDS);
    expect(backToDefault).not.toMatch(/max_tool_rounds:/);
  });

  it('preserves other agent_node keys when updating rounds', () => {
    const yaml = `${base}agent_node:\n  temperature: 0.2\n  max_tool_rounds: 8\n`;
    const next = applyManifestQuick(yaml, {
      ...parseManifestQuick(yaml),
      maxToolRounds: 18,
    });
    expect(parseManifestQuick(next).maxToolRounds).toBe(18);
    expect(next).toMatch(/temperature:\s*0\.2/);
  });

  it('reads last property without trailing newline', () => {
    const yaml = `${base.trimEnd()}\nagent_node:\n  max_tool_rounds: 17`;
    expect(parseManifestQuick(yaml).maxToolRounds).toBe(17);
  });

  it('updates an existing max_tool_rounds value without snapping to default', () => {
    const first = applyManifestQuick(base, {
      ...parseManifestQuick(base),
      maxToolRounds: 15,
    });
    const second = applyManifestQuick(first, {
      ...parseManifestQuick(first),
      maxToolRounds: 25,
    });
    expect(parseManifestQuick(second).maxToolRounds).toBe(25);
  });

  it('clamps to ceiling', () => {
    const yaml = applyManifestQuick(base, {
      ...parseManifestQuick(base),
      maxToolRounds: 999,
    });
    expect(parseManifestQuick(yaml).maxToolRounds).toBe(MAX_TOOL_ROUNDS_CEILING);
  });
});
