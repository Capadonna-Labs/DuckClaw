import { describe, expect, it } from 'vitest';
import { toolHeartbeatsFromActivity } from '@/lib/chatActivityHeartbeats';
import { isToolHeartbeatRunning } from '@/lib/toolHeartbeat';

describe('toolHeartbeatsFromActivity', () => {
  it('pairs start/done for the same tool', () => {
    const msgs = toolHeartbeatsFromActivity(
      [
        { kind: 'tool', tool_name: 'mcp__google_gmail__get_thread', tool_phase: 'start' },
        {
          kind: 'tool',
          tool_name: 'mcp__google_gmail__get_thread',
          tool_phase: 'done',
          elapsed_ms: 2400,
        },
        { kind: 'tool', tool_name: 'mcp__google_gmail__search_threads', tool_phase: 'start' },
        {
          kind: 'tool',
          tool_name: 'mcp__google_gmail__search_threads',
          tool_phase: 'done',
          elapsed_ms: 4800,
        },
      ],
      'quant_analyst'
    );
    expect(msgs).toHaveLength(2);
    expect(msgs.every((m) => !isToolHeartbeatRunning(m))).toBe(true);
    expect(msgs[0]?.toolElapsedMs).toBe(2400);
    expect(msgs[1]?.toolElapsedMs).toBe(4800);
  });

  it('leaves unpaired start as running', () => {
    const msgs = toolHeartbeatsFromActivity(
      [{ kind: 'tool', tool_name: 'foo', tool_phase: 'start' }],
      'w'
    );
    expect(msgs).toHaveLength(1);
    expect(isToolHeartbeatRunning(msgs[0]!)).toBe(true);
  });
});
