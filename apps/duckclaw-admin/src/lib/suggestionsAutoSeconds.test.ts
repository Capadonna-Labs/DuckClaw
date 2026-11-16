import { describe, expect, it } from 'vitest';
import { AUTO_SECONDS_DEFAULT, clampAutoSeconds } from './suggestionsAutoSeconds';

describe('suggestionsAutoSeconds', () => {
  it('clamps to 3..300 and falls back to the default', () => {
    expect(clampAutoSeconds(8)).toBe(8);
    expect(clampAutoSeconds('12')).toBe(12);
    expect(clampAutoSeconds(0)).toBe(3);
    expect(clampAutoSeconds(9999)).toBe(300);
    expect(clampAutoSeconds('abc')).toBe(AUTO_SECONDS_DEFAULT);
  });
});
