import { describe, expect, it } from 'vitest';
import { normalizeContextTokenBreakdown } from './contextTokenBreakdown';

describe('normalizeContextTokenBreakdown', () => {
  it('returns null for empty input', () => {
    expect(normalizeContextTokenBreakdown(null)).toBeNull();
    expect(normalizeContextTokenBreakdown({})).toBeNull();
  });

  it('fills total from parts when missing', () => {
    expect(
      normalizeContextTokenBreakdown({ system: 10, messages: 20, tools: 30 })
    ).toEqual({
      system: 10,
      messages: 20,
      tools: 30,
      tool_results: 0,
      tool_schemas: 0,
      total: 60,
    });
  });
});
