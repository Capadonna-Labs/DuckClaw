'use client';

export type PendingDetachedTurn = {
  chatId: string;
  tenantId: string;
  workerId: string;
  text: string;
  startedAt: number;
};

const KEY_PREFIX = 'duckclaw-admin-detached-turn-';

function key(chatId: string): string {
  return `${KEY_PREFIX}${chatId.trim()}`;
}

export function writePendingDetachedTurn(turn: PendingDetachedTurn): void {
  if (typeof window === 'undefined' || !turn.chatId.trim()) return;
  try {
    localStorage.setItem(key(turn.chatId), JSON.stringify(turn));
  } catch {
    /* ignore */
  }
}

export function readPendingDetachedTurn(chatId: string): PendingDetachedTurn | null {
  if (typeof window === 'undefined' || !chatId.trim()) return null;
  try {
    const raw = localStorage.getItem(key(chatId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<PendingDetachedTurn>;
    if (!parsed.chatId || !parsed.text || !parsed.startedAt) return null;
    if (Date.now() - Number(parsed.startedAt) > 30 * 60_000) {
      clearPendingDetachedTurn(chatId);
      return null;
    }
    return {
      chatId: String(parsed.chatId),
      tenantId: String(parsed.tenantId || 'default'),
      workerId: String(parsed.workerId || ''),
      text: String(parsed.text),
      startedAt: Number(parsed.startedAt),
    };
  } catch {
    return null;
  }
}

export function clearPendingDetachedTurn(chatId: string): void {
  if (typeof window === 'undefined' || !chatId.trim()) return;
  try {
    localStorage.removeItem(key(chatId));
  } catch {
    /* ignore */
  }
}
