import { describe, expect, it } from 'vitest';
import { parseDeliverable } from '@/components/reports/reportsPageViewUtils';

describe('parseDeliverable', () => {
  it('defaults to word', () => {
    expect(parseDeliverable(null)).toBe('word');
    expect(parseDeliverable('')).toBe('word');
    expect(parseDeliverable('word')).toBe('word');
  });

  it('parses html tab', () => {
    expect(parseDeliverable('html')).toBe('html');
  });
});

console.log('reportsPageView.test.ts OK');
