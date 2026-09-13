import { describe, expect, it } from 'vitest';
import type { ChatMsg } from '@/components/chat/types';
import {
  coalesceTrailingToolHeartbeats,
  findHeartbeatInsertIndex,
} from '@/components/chat/adminChatPure';

const tool = (name: string): ChatMsg => ({
  role: 'heartbeat',
  text: name,
  heartbeatKind: 'tool',
  toolName: name,
  toolPhase: 'done',
});

describe('findHeartbeatInsertIndex', () => {
  it('inserts before streaming assistant at end', () => {
    const msgs: ChatMsg[] = [
      { role: 'user', text: 'hola' },
      { role: 'assistant', text: '', streaming: true },
    ];
    expect(findHeartbeatInsertIndex(msgs)).toBe(1);
  });

  it('inserts before finished assistant when late tool heartbeats arrive', () => {
    const msgs: ChatMsg[] = [
      { role: 'user', text: 'hola' },
      { role: 'assistant', text: 'listo', streaming: false },
    ];
    expect(findHeartbeatInsertIndex(msgs)).toBe(1);
  });

  it('keeps tools before assistant when tools already present', () => {
    const msgs: ChatMsg[] = [
      { role: 'user', text: 'hola' },
      tool('read_sql'),
      { role: 'assistant', text: 'ok', streaming: false },
    ];
    expect(findHeartbeatInsertIndex(msgs)).toBe(2);
  });

  it('appends when turn has user but no assistant yet', () => {
    const msgs: ChatMsg[] = [{ role: 'user', text: 'hola' }];
    expect(findHeartbeatInsertIndex(msgs)).toBe(1);
  });
});

describe('coalesceTrailingToolHeartbeats', () => {
  it('moves tools that floated after the assistant back before it', () => {
    const msgs: ChatMsg[] = [
      { role: 'user', text: 'hola' },
      tool('early'),
      { role: 'assistant', text: 'listo', streaming: false },
      tool('late_a'),
      tool('late_b'),
    ];
    expect(
      coalesceTrailingToolHeartbeats(msgs).map(
        (m) => `${m.role}${m.toolName ? `:${m.toolName}` : ''}`
      )
    ).toEqual([
      'user',
      'heartbeat:early',
      'heartbeat:late_a',
      'heartbeat:late_b',
      'assistant',
    ]);
  });

  it('is a no-op when tools are already before the assistant', () => {
    const msgs: ChatMsg[] = [
      { role: 'user', text: 'hola' },
      tool('a'),
      { role: 'assistant', text: 'ok', streaming: false },
    ];
    expect(coalesceTrailingToolHeartbeats(msgs)).toEqual(msgs);
  });
});
