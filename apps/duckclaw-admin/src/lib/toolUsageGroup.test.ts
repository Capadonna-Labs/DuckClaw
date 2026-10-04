import { describe, expect, it } from 'vitest';
import type { ChatMsg } from '@/components/chat/types';
import {
  groupMessagesForDisplay,
  isToolHeartbeatMessage,
  toolGroupCurrentToolName,
  toolGroupHasRunning,
  toolGroupStableKey,
  toolGroupTotalElapsedMs,
  groupToolInvocationsByName,
  toolRowDurationLabel,
  groupInvocationsByWorker,
  toolGroupErrorCount,
} from './toolUsageGroup';

const tool = (name: string, phase: ChatMsg['toolPhase'] = 'done', elapsedMs?: number): ChatMsg => ({
  role: 'heartbeat',
  heartbeatKind: 'tool',
  toolName: name,
  toolPhase: phase,
  toolElapsedMs: elapsedMs ?? (phase === 'done' ? 10 : undefined),
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
      { kind: 'toolGroup', indices: [1, 2, 4] },
      { kind: 'message', index: 3 },
      { kind: 'message', index: 5 },
    ]);
  });

  it('one tool group per turn even with status between tools', () => {
    const status: ChatMsg = { role: 'heartbeat', heartbeatKind: 'status', text: 'PROGRESO…' };
    expect(
      groupMessagesForDisplay([
        user,
        tool('a'),
        status,
        tool('b'),
        tool('c'),
        assistant,
        { role: 'user', text: 'otro' },
        tool('d'),
        assistant,
      ])
    ).toEqual([
      { kind: 'message', index: 0 },
      { kind: 'toolGroup', indices: [1, 3, 4] },
      { kind: 'message', index: 2 },
      { kind: 'message', index: 5 },
      { kind: 'message', index: 6 },
      { kind: 'toolGroup', indices: [7] },
      { kind: 'message', index: 8 },
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

  it('reports running state and wall-clock elapsed (not sum)', () => {
    const running = [user, tool('fetch', 'running'), assistant];
    const group = groupMessagesForDisplay(running);
    const indices = (group[1] as { indices: number[] }).indices;
    expect(toolGroupHasRunning(running, indices)).toBe(true);
    expect(toolGroupTotalElapsedMs(running, indices)).toBeNull();

    const done = [user, tool('a'), tool('b', 'done')];
    done[1].toolElapsedMs = 5;
    done[1].toolStartedAt = 1000;
    done[2].toolElapsedMs = 7;
    done[2].toolStartedAt = 1003; // overlaps / follows — span = (1003+7) - 1000 = 10
    const g2 = groupMessagesForDisplay(done);
    expect(toolGroupTotalElapsedMs(done, (g2[1] as { indices: number[] }).indices)).toBe(10);

    // Sin startedAt: max individual, no suma
    const noStart = [user, tool('a', 'done', 5), tool('b', 'done', 7)];
    const g3 = groupMessagesForDisplay(noStart);
    expect(toolGroupTotalElapsedMs(noStart, (g3[1] as { indices: number[] }).indices)).toBe(7);
  });

  it('does not inflate elapsed with Date.now()-startedAt when toolElapsedMs missing', () => {
    const stale: ChatMsg = {
      role: 'heartbeat',
      heartbeatKind: 'tool',
      toolName: 'invoke_worker',
      toolPhase: 'done',
      toolStartedAt: Date.now() - 27 * 60_000,
      // toolElapsedMs deliberately missing (rehydrate / lost SSE field)
      text: 'Usando: invoke_worker',
    };
    const msgs = [user, stale];
    expect(toolGroupTotalElapsedMs(msgs, [1])).toBe(0);
    const grouped = groupToolInvocationsByName(msgs, [1]);
    expect(grouped[0]?.maxMs).toBeNull();
    expect(grouped[0]?.latestMs).toBeNull();
  });

  describe('groupToolInvocationsByName', () => {
    it('groups repeated tool invocations with count and averages', () => {
      const messages = [
        user,
        tool('read_sql', 'done', 100),
        tool('read_sql', 'done', 200),
        tool('read_sql', 'done', 150),
        tool('get_current_time', 'done', 50),
        assistant,
      ];
      const grouped = groupToolInvocationsByName(messages, [1, 2, 3, 4]);

      expect(grouped).toHaveLength(2);

      const readSqlGroup = grouped.find((g) => g.toolName === 'read_sql');
      expect(readSqlGroup).toBeDefined();
      expect(readSqlGroup?.count).toBe(3);
      expect(readSqlGroup?.latestMs).toBe(150);
      expect(readSqlGroup?.maxMs).toBe(200);
      expect(readSqlGroup?.averageMs).toBe(150); // (100 + 200 + 150) / 3
      expect(readSqlGroup?.isRunning).toBe(false);
      expect(readSqlGroup?.isError).toBe(false);

      const timeGroup = grouped.find((g) => g.toolName === 'get_current_time');
      expect(timeGroup).toBeDefined();
      expect(timeGroup?.count).toBe(1);
      expect(timeGroup?.latestMs).toBe(50);
      expect(timeGroup?.maxMs).toBe(50);
      expect(timeGroup?.averageMs).toBe(50);
    });

    it('handles running tools', () => {
      const messages = [
        user,
        tool('read_sql', 'done', 100),
        tool('read_sql', 'running'),
        assistant,
      ];
      const grouped = groupToolInvocationsByName(messages, [1, 2]);

      expect(grouped).toHaveLength(1);
      expect(grouped[0].count).toBe(2);
      expect(grouped[0].isRunning).toBe(true);
      expect(grouped[0].latestMs).toBe(100); // Solo cuenta el completado
      expect(grouped[0].maxMs).toBe(100);
      expect(grouped[0].averageMs).toBe(100);
    });

    it('detects errors in group', () => {
      const messages = [
        user,
        tool('read_sql', 'done', 100),
        tool('read_sql', 'error', 50),
        assistant,
      ];
      const grouped = groupToolInvocationsByName(messages, [1, 2]);

      expect(grouped).toHaveLength(1);
      expect(grouped[0].count).toBe(2);
      expect(grouped[0].isError).toBe(true);
    });

    it('handles single tool invocation', () => {
      const messages = [user, tool('read_sql', 'done', 100), assistant];
      const grouped = groupToolInvocationsByName(messages, [1]);

      expect(grouped).toHaveLength(1);
      expect(grouped[0].count).toBe(1);
      expect(grouped[0].toolName).toBe('read_sql');
      expect(grouped[0].latestMs).toBe(100);
      expect(grouped[0].maxMs).toBe(100);
      expect(grouped[0].averageMs).toBe(100);
    });
  });
});

describe('toolRowDurationLabel', () => {
  const base = { count: 1, latestMs: 177, maxMs: 177, averageMs: 177, isRunning: false };

  it('single call shows one duration', () => {
    expect(toolRowDurationLabel(base)).toEqual({ primary: '177ms', secondary: '' });
  });

  it('repeated calls with equal times do not repeat max/avg', () => {
    expect(toolRowDurationLabel({ ...base, count: 2, latestMs: 8, maxMs: 8, averageMs: 8 })).toEqual({
      primary: '8ms',
      secondary: '',
    });
  });

  it('repeated calls with different times show max and average', () => {
    expect(
      toolRowDurationLabel({ ...base, count: 3, latestMs: 120, maxMs: 900, averageMs: 400 })
    ).toEqual({ primary: '900ms', secondary: 'prom 400ms' });
  });

  it('running shows the live timer', () => {
    expect(toolRowDurationLabel({ ...base, isRunning: true }, 3200)).toEqual({
      primary: '3.20s',
      secondary: '',
    });
    expect(toolRowDurationLabel({ ...base, isRunning: true }, null).primary).toBe('');
  });
});

describe('agent grouping and errors', () => {
  const tool = (
    name: string,
    workerId: string,
    phase: 'done' | 'error' = 'done',
    detail?: string,
    startedAt = 1
  ): ChatMsg => ({
    role: 'heartbeat',
    heartbeatKind: 'tool',
    text: `Usando: ${name}`,
    toolName: name,
    toolPhase: phase,
    toolElapsedMs: 10,
    toolStartedAt: startedAt,
    workerId,
    toolDetail: detail,
  });

  it('splits the same tool run by two agents into separate rows, grouped by agent', () => {
    const msgs = [
      tool('read_sql', 'manager'),
      tool('read_sql', 'manager->worker_a'),
      tool('get_current_time', 'worker_a'),
    ];
    const rows = groupToolInvocationsByName(msgs, [0, 1, 2]);
    expect(rows.map((r) => `${r.worker}:${r.toolName}`)).toEqual([
      'manager:read_sql',
      'worker_a:read_sql',
      'worker_a:get_current_time',
    ]);
    expect(groupInvocationsByWorker(rows).map((b) => [b.worker, b.rows.length])).toEqual([
      ['manager', 1],
      ['worker_a', 2],
    ]);
  });

  it('events without worker fall back to the group identity instead of a phantom agent', () => {
    const msgs = [tool('read_sql', ''), tool('read_sql', 'worker_a')];
    const rows = groupToolInvocationsByName(msgs, [0, 1], 'worker_a');
    expect(rows).toHaveLength(1);
    expect(rows[0].count).toBe(2);
  });

  it('exposes error count and the newest error detail', () => {
    const msgs = [
      tool('execute_signal_with_bracket', 'worker_a', 'error', 'viejo', 1),
      tool('execute_signal_with_bracket', 'worker_a', 'done', undefined, 2),
      tool('execute_signal_with_bracket', 'worker_a', 'error', 'PRE_FLIGHT_MARK_UNAVAILABLE', 3),
    ];
    const [row] = groupToolInvocationsByName(msgs, [0, 1, 2]);
    expect(row.isError).toBe(true);
    expect(row.errorCount).toBe(2);
    expect(row.errorDetail).toBe('PRE_FLIGHT_MARK_UNAVAILABLE');
    expect(toolGroupErrorCount(msgs, [0, 1, 2])).toBe(2);
  });
});
