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

  it('places tools for in-flight turn (user without assistant) after that user', () => {
    const merged = interleaveEphemeralIntoHistory(
      [user('a'), assistant('A'), user('b')],
      [tool('read_sql', 2)]
    );
    expect(
      merged.map((m) => `${m.role}${m.toolName ? `:${m.toolName}` : ''}`)
    ).toEqual(['user', 'assistant', 'user', 'heartbeat:read_sql']);
    expect(merged[merged.length - 1]?.role).toBe('heartbeat');
  });

  it('clamps turn_user_index above server user count to the last user', () => {
    // Persist truncates at MAX_MSGS → tools tagged 25 with only 24 users in Redis.
    const merged = interleaveEphemeralIntoHistory(
      [user('a'), assistant('A'), user('b'), assistant('B')],
      [tool('read_sql', 99)]
    );
    expect(
      merged.map((m) => `${m.role}${m.toolName ? `:${m.toolName}` : ''}`)
    ).toEqual(['user', 'assistant', 'user', 'heartbeat:read_sql', 'assistant']);
  });

  it('does not append orphan tools after the last assistant', () => {
    const merged = interleaveEphemeralIntoHistory(
      [user('a'), assistant('A')],
      [tool('orphan')]
    );
    expect(merged.map((m) => m.role)).toEqual(['user', 'heartbeat', 'assistant']);
  });

  it('spreads legacy tools across existing turns instead of pinning all to the last turn', () => {
    const merged = interleaveEphemeralIntoHistory(
      [user('a'), assistant('A'), user('b'), assistant('B')],
      [tool('first_legacy'), tool('second_legacy')]
    );
    expect(
      merged.map((m) => `${m.role}${m.toolName ? `:${m.toolName}` : ''}`)
    ).toEqual([
      'user',
      'heartbeat:first_legacy',
      'assistant',
      'user',
      'heartbeat:second_legacy',
      'assistant',
    ]);
  });

  it('regression: anchored tools follow their turn when the capped window slides', () => {
    // Window at the cap: user positions are relative, so after one more turn the
    // oldest pair drops and every stored turnUserIndex points one turn later.
    // Before anchors, all of these piled onto the last turn in one growing box.
    const anchored = (name: string, idx: number, u: string, a: string): ChatMsg => ({
      ...tool(name, idx),
      anchorUser: u,
      anchorAssistant: a,
    });
    // Stored while the window was [a, b, c]: turn b = 2, turn c = 3.
    const ephemeral = [anchored('read_sql', 2, 'b', 'B'), anchored('list_skills', 3, 'c', 'C')];
    // Window slid: 'a' dropped, 'd' arrived.
    const server = [user('b'), assistant('B'), user('c'), assistant('C'), user('d'), assistant('D')];
    expect(
      interleaveEphemeralIntoHistory(server, ephemeral).map(
        (m) => `${m.role}${m.toolName ? `:${m.toolName}` : ''}${m.role === 'user' ? `:${m.text}` : ''}`
      )
    ).toEqual([
      'user:b',
      'heartbeat:read_sql',
      'assistant',
      'user:c',
      'heartbeat:list_skills',
      'assistant',
      'user:d',
      'assistant',
    ]);
  });

  it('drops anchored tools whose turn scrolled out of the window', () => {
    const gone: ChatMsg = { ...tool('old_tool', 3), anchorUser: 'a', anchorAssistant: 'A' };
    const server = [user('b'), assistant('B'), user('c'), assistant('C')];
    expect(interleaveEphemeralIntoHistory(server, [gone]).some((m) => m.toolName === 'old_tool')).toBe(
      false
    );
  });
});
