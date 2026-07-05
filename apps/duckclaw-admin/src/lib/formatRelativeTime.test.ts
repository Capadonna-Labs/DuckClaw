import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { formatRelativeTimeMs } from './formatRelativeTime';

describe('formatRelativeTimeMs', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-07-05T15:00:00.000Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('returns sin datos for empty timestamp', () => {
    expect(formatRelativeTimeMs(0)).toBe('sin datos');
    expect(formatRelativeTimeMs(null)).toBe('sin datos');
  });

  it('returns ahora for recent timestamps', () => {
    const now = Date.now();
    expect(formatRelativeTimeMs(now - 5_000)).toBe('ahora');
  });

  it('returns seconds and minutes', () => {
    const now = Date.now();
    expect(formatRelativeTimeMs(now - 30_000)).toBe('hace 30s');
    expect(formatRelativeTimeMs(now - 120_000)).toBe('hace 2m');
  });
});
