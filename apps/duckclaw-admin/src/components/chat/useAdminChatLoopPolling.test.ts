import { describe, expect, it } from 'vitest';

import type { ChatMsg } from '@/components/chat/types';
import {
  conversationIndicatesLoopScheduling,
  isLoopProgressHeartbeat,
} from '@/components/chat/useAdminChat';

describe('loop outbound polling helpers', () => {
  it('detects loop progress heartbeats', () => {
    expect(isLoopProgressHeartbeat('[loop] self_tick_dispatched')).toBe(true);
    expect(isLoopProgressHeartbeat('Pensando…')).toBe(false);
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
