import { describe, expect, it } from 'vitest';
import type { ChatMsg } from '@/components/chat/types';
import { findHeartbeatInsertIndex } from '@/components/chat/adminChatPure';

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
      {
        role: 'heartbeat',
        text: 'read_sql',
        heartbeatKind: 'tool',
        toolName: 'read_sql',
        toolPhase: 'done',
      },
      { role: 'assistant', text: 'ok', streaming: false },
    ];
    expect(findHeartbeatInsertIndex(msgs)).toBe(2);
  });

  it('appends when turn has user but no assistant yet', () => {
    const msgs: ChatMsg[] = [{ role: 'user', text: 'hola' }];
    expect(findHeartbeatInsertIndex(msgs)).toBe(1);
  });
});
