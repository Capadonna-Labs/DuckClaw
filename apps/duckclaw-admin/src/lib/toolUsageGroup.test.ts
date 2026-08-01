import { describe, expect, it } from 'vitest';
import type { ChatMsg } from '@/components/chat/types';
import {
  groupMessagesForDisplay,
  isToolHeartbeatMessage,
  toolGroupCurrentToolName,
  toolGroupHasRunning,
  toolGroupStableKey,
  toolGroupTotalElapsedMs,
} from './toolUsageGroup';

const tool = (name: string, phase: ChatMsg['toolPhase'] = 'done'): ChatMsg => ({
  role: 'heartbeat',
  heartbeatKind: 'tool',
  toolName: name,
  toolPhase: phase,
  toolElapsedMs: phase === 'done' ? 10 : undefined,
  text: `Usando: ${name}`,
});

const user: ChatMsg = { role: 'user', text: 'hola' };
const plan: ChatMsg = { role: 'heartbeat', heartbeatKind: 'plan', text: 'Plan…' };
const assistant: ChatMsg = { role: 'assistant', text: 'ok' };

describe('toolUsageGroup', () => {
  it('detects tool heartbeat messages', () => {
    expect(isToolHeartbeatMessage(tool('x'))).toBe(true);
    expect(isToolHeartbeatMessage(plan)).toBe(false);
  });

  it('groups three consecutive tools', () => {
    expect(
      groupMessagesForDisplay([
        user,
        tool('get_current_time'),
        tool('search_project_knowledge'),
        tool('tavily_search'),
        assistant,
      ])
    ).toEqual([
      { kind: 'message', index: 0 },
      { kind: 'toolGroup', indices: [1, 2, 3] },
      { kind: 'message', index: 4 },
    ]);
  });

  it('splits groups when plan interrupts tools', () => {
    expect(
      groupMessagesForDisplay([user, tool('a'), tool('b'), plan, tool('c'), assistant])
    ).toEqual([
      { kind: 'message', index: 0 },
      { kind: 'toolGroup', indices: [1, 2] },
      { kind: 'message', index: 3 },
      { kind: 'toolGroup', indices: [4] },
      { kind: 'message', index: 5 },
    ]);
  });

  it('wraps a single tool in a group', () => {
    expect(groupMessagesForDisplay([user, tool('read_sql'), assistant])[1]).toEqual({
      kind: 'toolGroup',
      indices: [1],
    });
  });

  it('stable key survives new tools in same turn', () => {
    const msgs = [user, tool('a'), tool('b'), assistant];
    const k1 = toolGroupStableKey(msgs, [1, 2]);
    const k2 = toolGroupStableKey([user, tool('c'), tool('a'), tool('b'), assistant], [1, 2, 3]);
    expect(k1).toBe('tool-group-turn-0');
    expect(k2).toBe('tool-group-turn-0');
  });

  it('current tool prefers running, else newest', () => {
    const running = tool('web_search', 'running');
    running.toolStartedAt = 100;
    const done = tool('get_current_time', 'done');
    done.toolStartedAt = 50;
    expect(toolGroupCurrentToolName([user, running, done], [1, 2])).toBe('web_search');
    expect(toolGroupCurrentToolName([user, done], [1])).toBe('get_current_time');
  });

  it('reports running state and total elapsed', () => {
    const running = [user, tool('fetch', 'running'), assistant];
    const group = groupMessagesForDisplay(running);
    const indices = (group[1] as { indices: number[] }).indices;
    expect(toolGroupHasRunning(running, indices)).toBe(true);
    expect(toolGroupTotalElapsedMs(running, indices)).toBeNull();

    const done = [user, tool('a'), tool('b', 'done')];
    done[1].toolElapsedMs = 5;
    done[2].toolElapsedMs = 7;
    const g2 = groupMessagesForDisplay(done);
    expect(toolGroupTotalElapsedMs(done, (g2[1] as { indices: number[] }).indices)).toBe(12);
  });
});
