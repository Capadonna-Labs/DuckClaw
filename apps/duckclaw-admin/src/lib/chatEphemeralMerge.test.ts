import { describe, expect, it } from 'vitest';
import type { ChatMsg } from '@/components/chat/types';
import { countUsersBefore, interleaveEphemeralIntoHistory } from './chatEphemeralMerge';

const user = (text: string): ChatMsg => ({ role: 'user', text });
const assistant = (text: string): ChatMsg => ({ role: 'assistant', text });
const tool = (name: string, turnUserIndex?: number): ChatMsg => ({
  role: 'heartbeat',
  heartbeatKind: 'tool',
  toolName: name,
  toolPhase: 'done',
  text: `Usando: ${name}`,
  turnUserIndex,
});

describe('chatEphemeralMerge', () => {
  it('countUsersBefore counts only prior user messages', () => {
    const msgs = [user('a'), tool('x'), assistant('A'), user('b')];
    expect(countUsersBefore(msgs, 1)).toBe(1);
    expect(countUsersBefore(msgs, 4)).toBe(2);
  });

  it('interleaves tools before matching assistant turn', () => {
    const server = [user('a'), assistant('A'), user('b'), assistant('B')];
    const ephemeral = [tool('read_sql', 1), tool('web_search', 1), tool('tavily', 2)];
    expect(
      interleaveEphemeralIntoHistory(server, ephemeral).map(
        (m) => `${m.role}${m.toolName ? `:${m.toolName}` : ''}`
      )
    ).toEqual([
      'user',
      'heartbeat:read_sql',
      'heartbeat:web_search',
      'assistant',
      'user',
      'heartbeat:tavily',
      'assistant',
    ]);
  });

  it('does not leave all tools at end when turnUserIndex is set', () => {
    const merged = interleaveEphemeralIntoHistory(
      [user('x'), assistant('y')],
      [tool('a', 1), tool('b', 1)]
    );
    expect(merged[merged.length - 1]?.role).toBe('assistant');
  });
});
