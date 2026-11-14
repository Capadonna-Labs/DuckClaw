import { describe, expect, it } from 'vitest';
import { groupReactions, nextUserReaction, withUserReaction } from '@/components/chat/useReactToMessage';
import { withAgentReaction, withInterimMessage } from '@/components/chat/adminChatPure';

describe('message reactions', () => {
  it('tapping the emoji already chosen removes it, another one replaces it', () => {
    const mine = [{ emoji: '👍', by: 'user' as const }];
    expect(nextUserReaction(mine, '👍')).toBeNull();
    expect(nextUserReaction(mine, '🔥')).toBe('🔥');
    expect(nextUserReaction(undefined, '🔥')).toBe('🔥');
  });

  it("changes only the user's reaction and keeps the agent's", () => {
    const before = [{ emoji: '👀', by: 'agent' as const }, { emoji: '👍', by: 'user' as const }];
    expect(withUserReaction(before, '🔥')).toEqual([{ emoji: '🔥', by: 'user' }, { emoji: '👀', by: 'agent' }]);
    expect(withUserReaction(before, null)).toEqual([{ emoji: '👀', by: 'agent' }]);
  });

  it('groups the same emoji from user and agent into one chip, user first', () => {
    const g = groupReactions([{ emoji: '👀', by: 'agent' }, { emoji: '👍', by: 'user' }, { emoji: '👍', by: 'agent' }]);
    expect(g).toEqual([{ emoji: '👍', mine: true, agent: true }, { emoji: '👀', mine: false, agent: true }]);
  });
});

describe('agent messages in the middle of a turn', () => {
  const turn = [
    { role: 'user' as const, text: 'Analiza X' },
    { role: 'assistant' as const, text: '', streaming: true },
  ];

  it('puts interim messages before the answer being written, in order', () => {
    const out = withInterimMessage(withInterimMessage(turn, 'Reviso eso'), ' Ya casi ');
    expect(out.map((m) => m.text)).toEqual(['Analiza X', 'Reviso eso', 'Ya casi', '']);
    expect(out[3].streaming).toBe(true);
    expect(withInterimMessage(turn, '  ')).toBe(turn);
  });

  it("puts the agent's emoji on the user's last message and keeps the user's own", () => {
    const mine = [{ ...turn[0], reactions: [{ emoji: '👍', by: 'user' as const }] }, turn[1]];
    const out = withAgentReaction(withAgentReaction(mine, '👀'), '🫡');
    expect(out[0].reactions).toEqual([{ emoji: '👍', by: 'user' }, { emoji: '🫡', by: 'agent' }]);
  });
});
