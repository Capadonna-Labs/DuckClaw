import type { ChatImagePreview, ChatMsg } from '@/components/chat/types';
import { artifactPreviewApiPath } from '@/lib/artifactPreview';
import { interleaveEphemeralIntoHistory } from '@/lib/chatEphemeralMerge';
import { normalizeUsageTokens, type UsageTokenBreakdown } from '@/lib/formatTokenCount';

/** True si, tras un turno, corresponde pedir sugerencias de continuación al backend. */
export function shouldFetchChatSuggestions(
  userText: string,
  assistantResponse: string,
  aborted: boolean
): boolean {
  if (aborted) return false;
  if (userText.trim().startsWith('/')) return false;
  return assistantResponse.trim().length > 0;
}

/** True si corresponde mostrar los chips (se ocultan mientras el usuario tipea). */
export function shouldShowSuggestionChips(
  suggestions: string[],
  loading: boolean,
  input: string
): boolean {
  return suggestions.length > 0 && !loading && input.trim() === '';
}

export function artifactImagePreview(
  tenantId: string,
  artifactId: string
): ChatImagePreview[] {
  const tid = (tenantId || 'default').trim() || 'default';
  const aid = artifactId.trim();
  return [
    {
      url: artifactPreviewApiPath(tid, aid),
      name: `${aid}.png`,
      artifactId: aid,
      tenantId: tid,
    },
  ];
}

/** Heartbeats/plan/tool no están en Redis; conservarlos si recargamos historial en vivo. */
export function mergeHistoryWithEphemeral(server: ChatMsg[], ephemeral: ChatMsg[]): ChatMsg[] {
  if (!ephemeral.length) return server;
  return interleaveEphemeralIntoHistory(server, ephemeral);
}

export function collectEphemeralMessages(messages: ChatMsg[]): ChatMsg[] {
  return messages.filter((m) => m.role === 'heartbeat');
}

/** True si hay heartbeat de herramienta en el turno actual (entre último user y assistant streaming). */
export function hasToolHeartbeatInCurrentTurn(messages: ChatMsg[]): boolean {
  const streamIdx = messages.findIndex(
    (x, i) => x.role === 'assistant' && x.streaming && i === messages.length - 1
  );
  const end = streamIdx >= 0 ? streamIdx : messages.length;
  for (let i = end - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role === 'user') break;
    if (m.role === 'heartbeat' && m.heartbeatKind === 'tool') return true;
  }
  return false;
}

/** No renderizar burbuja assistant vacía mientras hay tool heartbeats (ThinkingBubble solo sin tools). */
export function shouldSkipEmptyStreamingAssistant(
  message: ChatMsg,
  messages: ChatMsg[]
): boolean {
  if (message.role !== 'assistant' || !message.streaming) return false;
  if ((message.text || '').trim()) return false;
  if (message.imagePreviews?.length) return false;
  return hasToolHeartbeatInCurrentTurn(messages);
}

export function isThinkingStatusHeartbeat(m: ChatMsg | undefined): boolean {
  return (
    m?.role === 'heartbeat' &&
    m.heartbeatKind === 'status' &&
    /^Pensando/i.test((m.text || '').trim())
  );
}

/** Remove stale "Pensando…" status heartbeats from persisted chat history. */
export function stripThinkingStatusHeartbeats(messages: ChatMsg[]): ChatMsg[] {
  return messages.filter((m) => !isThinkingStatusHeartbeat(m));
}

/** Server history includes loop system user turn plus assistant reply. */
export function isLoopSystemUserMessage(text: string): boolean {
  const t = (text || '').trim();
  if (!t) return false;
  if (t.includes('[Ciclo loop]') || t.includes('[Ciclo meditate]')) return true;
  if (!t.includes('[SYSTEM_EVENT')) return false;
  return /\/(loop|meditate)\b/i.test(t);
}

export function conversationHasLoopResult(messages: ChatMsg[]): boolean {
  return (
    messages.some((m) => m.role === 'user' && isLoopSystemUserMessage(m.text || '')) &&
    messages.some((m) => m.role === 'assistant')
  );
}

export function isLoopProgressHeartbeat(text: string): boolean {
  const t = text || '';
  return (
    t.includes('[loop]') ||
    t.includes('[meditate]') ||
    t.includes('[loop] active_mode_started') ||
    t.includes('[loop] self_tick_dispatched') ||
    t.includes('[meditate] active_mode_started') ||
    t.includes('[meditate] self_tick_dispatched')
  );
}

/** True si el hilo indica /loop activo (footer o status reciente). */
export function conversationIndicatesLoopScheduling(messages: ChatMsg[]): boolean {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role !== 'assistant') continue;
    const t = (m.text || '').toLowerCase();
    if (t.includes('modo /loop:** inactivo') || t.includes('modo /loop: inactivo')) {
      return false;
    }
    if (t.includes('modo /loop activo') || t.includes('próximo ciclo /loop')) {
      return true;
    }
    if (t.includes('/loop off') || t.includes('detenido')) {
      return false;
    }
  }
  return false;
}

export function workerStorageKey(chatId: string): string {
  return `duckclaw-admin-worker-${chatId}`;
}

export function revokeMessageImagePreviews(messages: ChatMsg[]): void {
  for (const m of messages) {
    if (!m.imagePreviews?.length) continue;
    for (const img of m.imagePreviews) {
      if (!img.url.startsWith('blob:')) continue;
      try {
        URL.revokeObjectURL(img.url);
      } catch {
        /* ignore */
      }
    }
  }
}

export function readStoredWorker(chatId: string): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return sessionStorage.getItem(workerStorageKey(chatId));
  } catch {
    return null;
  }
}

export type TurnTokenMeta = {
  usage_tokens?: Record<string, number> | null;
  context_estimated_tokens?: number | null;
};

/** Header mirrors gateway log line: last turn usage_tokens, not session sum. */
export function applyLastTurnTokenDisplay(
  setLastTurnUsage: (value: UsageTokenBreakdown | null) => void,
  setContextEstimatedTokens: (value: number | null) => void,
  meta: TurnTokenMeta
): void {
  const usage = normalizeUsageTokens(meta.usage_tokens);
  if (usage) {
    setLastTurnUsage(usage);
    setContextEstimatedTokens(null);
    return;
  }
  const ctx = meta.context_estimated_tokens;
  if (ctx != null && Number.isFinite(ctx) && ctx >= 0) {
    setLastTurnUsage(null);
    setContextEstimatedTokens(Math.floor(ctx));
  }
}
