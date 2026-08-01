/** Agrupa heartbeats tool consecutivos para render en caja desplegable. */

import type { ChatMsg } from '@/components/chat/types';
import {
  formatToolDisplayName,
  isToolHeartbeatRunning,
  parseToolNameFromHeartbeatText,
} from '@/lib/toolHeartbeat';

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

/** Clave estable por turno: no cambia al añadir tools al mismo grupo. */
export function toolGroupStableKey(messages: ChatMsg[], indices: number[]): string {
  const start = indices[0] ?? 0;
  for (let j = start - 1; j >= 0; j--) {
    if (messages[j]?.role === 'user') return `tool-group-turn-${j}`;
  }
  const oldest = messages[indices[indices.length - 1] ?? start];
  const id = oldest?.toolInvocationId ?? oldest?.toolStartedAt ?? start;
  return `tool-group-orphan-${id}`;
}

function toolDisplayName(m: ChatMsg): string {
  return formatToolDisplayName(
    (m.toolName || '').trim() || parseToolNameFromHeartbeatText(m.text || '') || 'tool'
  );
}

function newestByStartedAt(items: ChatMsg[]): ChatMsg | null {
  return items.reduce<ChatMsg | null>((best, m) => {
    if (!best) return m;
    return (m.toolStartedAt ?? 0) >= (best.toolStartedAt ?? 0) ? m : best;
  }, null);
}

/** Tool en curso (running) o la más reciente del grupo — para header colapsado. */
export function toolGroupCurrentToolName(messages: ChatMsg[], indices: number[]): string {
  const items = indices.map((i) => messages[i]).filter(isToolHeartbeatMessage);
  if (!items.length) return '';
  const running = items.filter((m) => isToolHeartbeatRunning(m));
  const target = newestByStartedAt(running.length ? running : items);
  return target ? toolDisplayName(target) : '';
}
