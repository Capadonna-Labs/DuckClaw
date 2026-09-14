import { describe, expect, it } from 'vitest';
import { formatCompactTokenCount, inferModelContextWindow } from './modelContextWindow';

describe('inferModelContextWindow', () => {
  it('resolves common Claude / GPT windows', () => {
    expect(inferModelContextWindow('claude-sonnet-4-20250514')).toBe(1_000_000);
    expect(inferModelContextWindow('claude-3-5-sonnet-latest')).toBe(200_000);
    expect(inferModelContextWindow('gpt-4o-mini')).toBe(128_000);
    expect(inferModelContextWindow('unknown-local-gguf')).toBeNull();
    expect(inferModelContextWindow('')).toBeNull();
  });
});

describe('formatCompactTokenCount', () => {
  it('compacts thousands and millions', () => {
    expect(formatCompactTokenCount(0)).toBe('0');
    expect(formatCompactTokenCount(999)).toBe('999');
    expect(formatCompactTokenCount(1200)).toBe('1.2k');
    expect(formatCompactTokenCount(381458)).toBe('381k');
    expect(formatCompactTokenCount(1_000_000)).toBe('1M');
  });
});
