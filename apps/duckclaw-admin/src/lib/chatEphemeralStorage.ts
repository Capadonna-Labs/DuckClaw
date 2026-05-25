/** Heartbeats/plan/tool SSE: no están en Redis; persistencia por chat en sessionStorage. */

import type { ChatMsg } from '@/components/chat/types';

const KEY_PREFIX = 'duckclaw-admin-chat-ephemeral-';

function storageKey(chatId: string): string {
  return `${KEY_PREFIX}${chatId.trim()}`;
}

function isEphemeralMessage(m: ChatMsg): boolean {
  return m.role === 'heartbeat';
}

/** Dedupe por toolName (último gana) + mensajes no-tool al final. */
export function mergeEphemeralHeartbeats(a: ChatMsg[], b: ChatMsg[]): ChatMsg[] {
  const combined = [...a, ...b].filter(isEphemeralMessage);
  if (!combined.length) return [];
  const toolByName = new Map<string, ChatMsg>();
  const other: ChatMsg[] = [];
  for (const m of combined) {
    if (m.heartbeatKind === 'tool' && m.toolName) {
      toolByName.set(m.toolName, m);
    } else {
      other.push(m);
    }
  }
  return [...other, ...toolByName.values()];
}

export function readEphemeralHeartbeats(chatId: string): ChatMsg[] {
  if (typeof window === 'undefined' || !chatId.trim()) return [];
  try {
    const raw = sessionStorage.getItem(storageKey(chatId));
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (m): m is ChatMsg =>
        typeof m === 'object' &&
        m !== null &&
        (m as ChatMsg).role === 'heartbeat'
    );
  } catch {
    return [];
  }
}

export function writeEphemeralHeartbeats(chatId: string, messages: ChatMsg[]): void {
  if (typeof window === 'undefined' || !chatId.trim()) return;
  const ephemeral = messages.filter(isEphemeralMessage);
  try {
    const key = storageKey(chatId);
    if (!ephemeral.length) {
      sessionStorage.removeItem(key);
      return;
    }
    sessionStorage.setItem(key, JSON.stringify(ephemeral));
  } catch {
    /* ignore quota */
  }
}

export function clearEphemeralHeartbeats(chatId: string): void {
  if (typeof window === 'undefined' || !chatId.trim()) return;
  try {
    sessionStorage.removeItem(storageKey(chatId));
  } catch {
    /* ignore */
  }
}
