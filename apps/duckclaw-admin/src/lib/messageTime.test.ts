import { describe, expect, it } from 'vitest';
import { formatMessageTime } from './messageTime';

describe('formatMessageTime', () => {
  it('shows only the time today and adds the date otherwise; empty without a time', () => {
    const now = new Date(2026, 9, 19, 12, 0);
    expect(formatMessageTime(new Date(2026, 9, 19, 9, 5).toISOString(), now)).not.toMatch(/oct/);
    expect(formatMessageTime(new Date(2026, 9, 18, 23, 45).toISOString(), now)).toMatch(/18/);
    expect(formatMessageTime(undefined, now)).toBe('');
    expect(formatMessageTime('nope', now)).toBe('');
  });
});
