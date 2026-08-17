/** Heartbeats/plan/tool SSE: no están en Redis; persistencia por chat+worker en sessionStorage. */

import type { ChatMsg } from '@/components/chat/types';
import { countUsersBefore } from '@/lib/chatEphemeralMerge';
import { isLoopProgressHeartbeat } from '@/components/chat/adminChatPure';
import { toolHeartbeatInvocationKey } from '@/lib/toolHeartbeat';
import { normalizeWorkerKey, workerMatches } from '@/lib/workerOptions';

const KEY_PREFIX = 'duckclaw-admin-chat-ephemeral-';

function legacyStorageKey(chatId: string): string {
  return `${KEY_PREFIX}${chatId.trim()}`;
}

function storageKey(chatId: string, workerId: string): string {
  const cid = chatId.trim();
  const wid = normalizeWorkerKey(workerId);
  if (!cid) return '';
  if (!wid) return legacyStorageKey(cid);
  return `${KEY_PREFIX}${cid}-${wid}`;
}

/** Canonical + legacy slug keys for chat (pre-normalize writes still readable). */
function allStorageKeysForChat(chatId: string, workerId: string): string[] {
  const cid = chatId.trim();
  if (!cid) return [];
  const keys = new Set<string>([legacyStorageKey(cid)]);
  if (workerId.trim()) keys.add(storageKey(chatId, workerId));
  const prefix = `${KEY_PREFIX}${cid}-`;
  try {
    for (let i = 0; i < sessionStorage.length; i++) {
      const k = sessionStorage.key(i);
      if (k?.startsWith(prefix)) keys.add(k);
    }
  } catch {
    /* ignore */
  }
  return [...keys];
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

function ephemeralDedupeKey(m: ChatMsg): string | null {
  if (m.heartbeatKind === 'tool' && m.toolName) {
    return toolHeartbeatInvocationKey(m) || `${m.toolName}@${m.toolStartedAt ?? ''}`;
  }
  const text = (m.text || '').trim();
  if (!text) return null;
  if (m.heartbeatKind === 'loop_tick' || isLoopProgressHeartbeat(text)) {
    return `loop:${text.slice(0, 240)}`;
  }
  if (m.heartbeatKind === 'status' && /^Pensando/i.test(text)) {
    return 'status:pensando';
  }
  if (m.heartbeatKind === 'plan') {
    return `plan:${text.slice(0, 240)}`;
  }
  return `${m.heartbeatKind || 'status'}:${text.slice(0, 240)}`;
}

/** Dedupe por invocación de tool; status/loop/plan por texto estable. */
export function mergeEphemeralHeartbeats(a: ChatMsg[], b: ChatMsg[]): ChatMsg[] {
  const combined = [...a, ...b].filter(isEphemeralMessage);
  if (!combined.length) return [];
  const byKey = new Map<string, ChatMsg>();
  const orderedKeys: string[] = [];
  for (const m of combined) {
    const key = ephemeralDedupeKey(m) || `other@${orderedKeys.length}`;
    if (!byKey.has(key)) orderedKeys.push(key);
    byKey.set(key, m);
  }
  return orderedKeys.map((k) => byKey.get(k)!).filter(Boolean);
}

function parseStoredHeartbeats(raw: string | null): ChatMsg[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (m): m is ChatMsg =>
        typeof m === 'object' && m !== null && (m as ChatMsg).role === 'heartbeat'
    );
  } catch {
    return [];
  }
}

export function readEphemeralHeartbeats(chatId: string, workerId = ''): ChatMsg[] {
  if (typeof window === 'undefined' || !chatId.trim()) return [];
  // La clave ya está acotada al worker; no se re-filtra por m.workerId (el gateway
  // manda un worker_id que no siempre coincide con el id de la UI).
  const keys = workerId.trim()
    ? [storageKey(chatId, workerId), legacyStorageKey(chatId)]
    : [legacyStorageKey(chatId)];
  const out: ChatMsg[] = [];
  const seen = new Set<string>();
  for (const key of keys) {
    for (const m of parseStoredHeartbeats(sessionStorage.getItem(key))) {
      const id =
        toolHeartbeatInvocationKey(m) ||
        `${m.toolName || ''}|${m.toolStartedAt || ''}|${m.text || ''}|${out.length}`;
      if (seen.has(id)) continue;
      seen.add(id);
      out.push(m);
    }
  }
  return out;
}

export function writeEphemeralHeartbeats(
  chatId: string,
  workerId: string,
  messages: ChatMsg[]
): void {
  if (typeof window === 'undefined' || !chatId.trim()) return;
  // ponytail: remount post-reload empieza con messages=[]; no borrar sessionStorage
  // o se pierden tools antes de mergeHistory. Clear explícito vía clearEphemeralHeartbeats.
  if (messages.length === 0) return;
  // El worker_id que llega por SSE no siempre normaliza igual que el id de la UI,
  // así que filtrar aquí descartaba todos los heartbeats. La clave ya acota al worker.
  const ephemeral: ChatMsg[] = [];
  for (let i = 0; i < messages.length; i++) {
    const m = messages[i];
    if (m.role !== 'heartbeat') continue;
    ephemeral.push({ ...m, turnUserIndex: countUsersBefore(messages, i) });
  }
  try {
    const key = storageKey(chatId, workerId);
    if (!key) return;
    // Historial sin heartbeats no borra: el clear explícito es clearEphemeralHeartbeats.
    if (!ephemeral.length) return;
    sessionStorage.setItem(key, JSON.stringify(ephemeral));
  } catch {
    /* ignore quota */
  }
}

export function clearEphemeralHeartbeats(chatId: string, workerId = ''): void {
  if (typeof window === 'undefined' || !chatId.trim()) return;
  try {
    if (workerId.trim()) {
      for (const key of allStorageKeysForChat(chatId, workerId)) {
        sessionStorage.removeItem(key);
      }
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
