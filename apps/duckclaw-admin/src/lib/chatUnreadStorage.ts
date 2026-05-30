import type { ChatMsg } from '@/components/chat/types';

export type LastReadState = {
  /** Índice del último mensaje visto en el array de mensajes. */
  messageIndex: number;
};

export function lastReadStorageKey(sessionId: string): string {
  return `duckclaw-admin-last-read-${sessionId}`;
}

export function readLastRead(sessionId: string): LastReadState | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = localStorage.getItem(lastReadStorageKey(sessionId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as { messageIndex?: unknown };
    if (typeof parsed.messageIndex === 'number' && parsed.messageIndex >= -1) {
      return { messageIndex: parsed.messageIndex };
    }
  } catch {
    /* ignore */
  }
  return null;
}

export function writeLastRead(sessionId: string, messageIndex: number): void {
  if (typeof window === 'undefined') return;
  try {
    localStorage.setItem(
      lastReadStorageKey(sessionId),
      JSON.stringify({ messageIndex } satisfies LastReadState)
    );
  } catch {
    /* ignore quota */
  }
}

/** Índice del último mensaje que cuenta como "visto" al abrir el panel. */
export function markReadMessageIndex(messages: ChatMsg[]): number {
  if (messages.length === 0) return -1;
  let idx = messages.length - 1;
  const last = messages[idx];
  // No marcar la burbuja assistant en streaming: al completar debe contar como no leída
  // si el usuario cerró el panel mientras el agente respondía.
  if (last?.role === 'assistant' && last.streaming) {
    idx -= 1;
  }
  return idx;
}

/** Mensajes assistant completados después del watermark. */
export function countUnreadAssistantMessages(
  messages: ChatMsg[],
  lastReadIndex: number
): number {
  let count = 0;
  for (let i = lastReadIndex + 1; i < messages.length; i++) {
    const m = messages[i];
    if (m.role === 'assistant' && !m.streaming) count += 1;
  }
  return count;
}

export function formatUnreadBadge(count: number): string {
  if (count <= 0) return '';
  return count > 99 ? '99+' : String(count);
}
