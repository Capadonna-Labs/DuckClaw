import { beforeEach, describe, expect, it } from 'vitest';
import { markConversationSeen, unreadReplies } from './conversationSeen';

describe('conversation unread badge', () => {
  beforeEach(() => {
    const store = new Map<string, string>();
    (globalThis as { window?: unknown }).window = {
      localStorage: {
        getItem: (k: string) => store.get(k) ?? null,
        setItem: (k: string, v: string) => void store.set(k, v),
      },
    };
  });

  it('starts read, counts new replies (user line + reply = 1), clears when opened', () => {
    expect(unreadReplies('c1', 10)).toBe(0); // first sight on this device
    expect(unreadReplies('c1', 14)).toBe(2); // two proactive turns since
    markConversationSeen('c1', 14); // chat opened
    expect(unreadReplies('c1', 14)).toBe(0);
    markConversationSeen('c1', 12); // an older fetch never moves it back
    expect(unreadReplies('c1', 14)).toBe(0);
  });
});
