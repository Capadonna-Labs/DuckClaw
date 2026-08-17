import { describe, expect, it } from 'vitest';

import type { ChatMsg } from '@/components/chat/types';
import {
  conversationHasLoopResult,
  conversationIndicatesLoopScheduling,
  isLoopProgressHeartbeat,
  isLoopSystemUserMessage,
} from '@/components/chat/useAdminChat';
import { mergeEphemeralHeartbeats } from '@/lib/chatEphemeralStorage';

describe('loop outbound polling helpers', () => {
  it('detects loop progress heartbeats', () => {
    expect(isLoopProgressHeartbeat('[loop] self_tick_dispatched')).toBe(true);
    expect(isLoopProgressHeartbeat('Pensando…')).toBe(false);
  });

  it('detects SYSTEM_EVENT loop user turns as loop result', () => {
    expect(
      isLoopSystemUserMessage('[SYSTEM_EVENT: Ciclo de auto-mejora programado /loop.')
    ).toBe(true);
    const messages: ChatMsg[] = [
      {
        role: 'user',
        text: '[SYSTEM_EVENT: Ciclo de auto-mejora programado /loop. Metas: P2 …]',
      },
      { role: 'assistant', text: 'Diagnóstico ALINEADO' },
    ];
    expect(conversationHasLoopResult(messages)).toBe(true);
  });

  it('dedupes duplicate loop progress heartbeats on merge', () => {
    const hb: ChatMsg = {
      role: 'heartbeat',
      heartbeatKind: 'status',
      text: '## /loop · Diagnóstico\nEstado: ALINEADO',
    };
    const merged = mergeEphemeralHeartbeats([hb], [{ ...hb }]);
    expect(merged).toHaveLength(1);
  });

  it('detects active loop from assistant footer', () => {
    const messages: ChatMsg[] = [
      {
        role: 'assistant',
        text: '⏭️ **Modo /loop activo** — ciclo en curso; próximo ciclo ~14:08 COT',
      },
    ];
    expect(conversationIndicatesLoopScheduling(messages)).toBe(true);
  });

  it('detects inactive loop after off', () => {
    const messages: ChatMsg[] = [
      { role: 'assistant', text: '⏭️ **Modo /loop:** inactivo.' },
    ];
    expect(conversationIndicatesLoopScheduling(messages)).toBe(false);
  });
});
