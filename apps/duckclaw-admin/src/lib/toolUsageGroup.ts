/** Agrupa heartbeats tool consecutivos para render en caja desplegable. */

import type { ChatMsg } from '@/components/chat/types';
import { isToolHeartbeatRunning } from '@/lib/toolHeartbeat';

export type ChatDisplayItem =
  | { kind: 'message'; index: number }
  | { kind: 'toolGroup'; indices: number[] };

export function isToolHeartbeatMessage(m: ChatMsg | undefined): boolean {
  return m?.role === 'heartbeat' && m.heartbeatKind === 'tool';
}

export function groupMessagesForDisplay(messages: ChatMsg[]): ChatDisplayItem[] {
  const out: ChatDisplayItem[] = [];
  let i = 0;
  while (i < messages.length) {
    if (!isToolHeartbeatMessage(messages[i])) {
      out.push({ kind: 'message', index: i });
      i += 1;
      continue;
    }
    const indices: number[] = [i];
    i += 1;
    while (i < messages.length && isToolHeartbeatMessage(messages[i])) {
      indices.push(i);
      i += 1;
    }
    out.push({ kind: 'toolGroup', indices });
  }
  return out;
}

export function toolGroupHasRunning(messages: ChatMsg[], indices: number[]): boolean {
  return indices.some((idx) => isToolHeartbeatRunning(messages[idx]));
}

export function toolGroupTotalElapsedMs(messages: ChatMsg[], indices: number[]): number | null {
  let total = 0;
  let any = false;
  for (const idx of indices) {
    const m = messages[idx];
    if (isToolHeartbeatRunning(m)) return null;
    const ms =
      m.toolElapsedMs ??
      (m.toolStartedAt != null ? Math.max(0, Date.now() - m.toolStartedAt) : undefined);
    if (ms != null && Number.isFinite(ms)) {
      total += ms;
      any = true;
    }
  }
  return any ? total : null;
}
