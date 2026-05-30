/** Heartbeats/plan/tool SSE: no están en Redis; persistencia por chat+worker en sessionStorage. */

import type { ChatMsg } from '@/components/chat/types';
import { workerMatches } from '@/lib/workerOptions';

const KEY_PREFIX = 'duckclaw-admin-chat-ephemeral-';

function legacyStorageKey(chatId: string): string {
  return `${KEY_PREFIX}${chatId.trim()}`;
}

function storageKey(chatId: string, workerId: string): string {
  const cid = chatId.trim();
  const wid = workerId.trim();
  if (!cid) return '';
  if (!wid) return legacyStorageKey(cid);
  return `${KEY_PREFIX}${cid}-${wid}`;
}

function isEphemeralMessage(m: ChatMsg): boolean {
  return m.role === 'heartbeat';
}

/** Solo heartbeats del worker activo (o sin workerId en mensaje legacy). */
export function filterEphemeralForWorker(messages: ChatMsg[], workerId: string): ChatMsg[] {
  const wid = workerId.trim();
  if (!wid) return messages.filter(isEphemeralMessage);
  return messages.filter(
    (m) => !isEphemeralMessage(m) || !m.workerId || workerMatches(m.workerId, wid)
  );
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
  return [...other, ...Array.from(toolByName.values())];
}

export function readEphemeralHeartbeats(chatId: string, workerId = ''): ChatMsg[] {
  if (typeof window === 'undefined' || !chatId.trim()) return [];
  const keys = workerId.trim()
    ? [storageKey(chatId, workerId)]
    : [legacyStorageKey(chatId)];
  const out: ChatMsg[] = [];
  for (const key of keys) {
    try {
      const raw = sessionStorage.getItem(key);
      if (!raw) continue;
      const parsed = JSON.parse(raw) as unknown;
      if (!Array.isArray(parsed)) continue;
      out.push(
        ...parsed.filter(
          (m): m is ChatMsg =>
            typeof m === 'object' &&
            m !== null &&
            (m as ChatMsg).role === 'heartbeat'
        )
      );
    } catch {
      /* ignore corrupt */
    }
  }
  return filterEphemeralForWorker(out, workerId);
}

export function writeEphemeralHeartbeats(
  chatId: string,
  workerId: string,
  messages: ChatMsg[]
): void {
  if (typeof window === 'undefined' || !chatId.trim()) return;
  const ephemeral = filterEphemeralForWorker(
    messages.filter(isEphemeralMessage),
    workerId
  );
  try {
    const key = storageKey(chatId, workerId);
    if (!ephemeral.length) {
      sessionStorage.removeItem(key);
      return;
    }
    sessionStorage.setItem(key, JSON.stringify(ephemeral));
  } catch {
    /* ignore quota */
  }
}

export function clearEphemeralHeartbeats(chatId: string, workerId = ''): void {
  if (typeof window === 'undefined' || !chatId.trim()) return;
  try {
    if (workerId.trim()) {
      sessionStorage.removeItem(storageKey(chatId, workerId));
      return;
    }
    sessionStorage.removeItem(legacyStorageKey(chatId));
  } catch {
    /* ignore */
  }
}

/** Elimina clave legacy (solo chatId) tras migrar a claves con worker. */
export function clearLegacyEphemeralHeartbeats(chatId: string): void {
  clearEphemeralHeartbeats(chatId);
}
