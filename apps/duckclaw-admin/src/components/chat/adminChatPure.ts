import type { ChatImagePreview, ChatMsg } from '@/components/chat/types';
import { artifactPreviewApiPath } from '@/lib/artifactPreview';
import { interleaveEphemeralIntoHistory } from '@/lib/chatEphemeralMerge';
import { normalizeUsageTokens, type UsageTokenBreakdown } from '@/lib/formatTokenCount';
import {
  normalizeContextTokenBreakdown,
  type ContextTokenBreakdown,
} from '@/lib/contextTokenBreakdown';

/**
 * Slash de configuración / ack corto (sin chips).
 * Comandos agente (`/execute-broker-signals`, …) con respuesta real SÍ piden chips.
 * Los ciclos /loop llegan como SYSTEM_EVENT / [Ciclo loop] (no empiezan por `/`).
 */
export function isFlyConfigSlashAck(userText: string): boolean {
  const t = (userText || '').trim();
  if (!t.startsWith('/')) return false;
  return (
    /^\/(loop|meditate)(\s|$)/i.test(t) ||
    /^\/(summarize|sandbox|help|status|voice|tts)\b/i.test(t)
  );
}

/** True si, tras un turno, corresponde pedir sugerencias de continuación al backend. */
export function shouldFetchChatSuggestions(
  userText: string,
  assistantResponse: string,
  aborted: boolean
): boolean {
  if (aborted) return false;
  if (!assistantResponse.trim()) return false;
  // Fly config acks (/loop on, /summarize, …) no piden chips.
  // Slash que invocan al worker con respuesta útil (/execute-…) sí.
  if (isFlyConfigSlashAck(userText)) return false;
  return true;
}

/**
 * True si hay sugerencias que mostrar en el dropdown fijo encima del input.
 * Se limpian al enviar un mensaje y se regeneran al terminar la respuesta del worker.
 */
export function shouldShowSuggestionChips(
  suggestions: string[],
  _loading?: boolean,
  _input?: string
): boolean {
  return suggestions.length > 0;
}

/** Clave estable del último intercambio para saber cuándo regenerar chips. */
export function suggestionsExchangeKey(
  chatId: string,
  userText: string,
  assistantText: string
): string {
  return `${chatId}:${userText}\0${assistantText.slice(0, 500)}`;
}

/** Último par user→assistant usable para regenerar chips (historial o post-turno). */
export function lastUserAssistantExchange(
  messages: ChatMsg[]
): { userText: string; assistantText: string } | null {
  let assistantText = '';
  let userText = '';
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i];
    if (!assistantText && m.role === 'assistant') {
      const t = (m.text || '').trim();
      if (t && !m.streaming) assistantText = t;
      continue;
    }
    if (assistantText && !userText && m.role === 'user') {
      const t = (m.text || '').trim();
      if (t) userText = t;
      break;
    }
  }
  if (!userText || !assistantText) return null;
  if (!shouldFetchChatSuggestions(userText, assistantText, false)) return null;
  return { userText, assistantText };
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
  if (!ephemeral.length) return coalesceTrailingToolHeartbeats(server);
  return coalesceTrailingToolHeartbeats(interleaveEphemeralIntoHistory(server, ephemeral));
}

/**
 * Si Redis aún no tiene el user del turno en vuelo (o un poll stale del turno
 * anterior reemplazó el estado), re-adjunta ese user + tools/assistant locales.
 */
export function preserveInFlightOptimisticTurn(
  server: ChatMsg[],
  prev: ChatMsg[],
  pendingText?: string
): ChatMsg[] {
  const pending = (pendingText || '').trim();
  if (!pending || !prev.length) return server;

  const serverHasPending = server.some(
    (m) => m.role === 'user' && (m.text || '').trim() === pending
  );
  if (serverHasPending) return server;

  let userIdx = -1;
  for (let i = prev.length - 1; i >= 0; i--) {
    if (prev[i]?.role === 'user' && (prev[i]?.text || '').trim() === pending) {
      userIdx = i;
      break;
    }
  }
  if (userIdx < 0) return server;

  return [...server, ...prev.slice(userIdx)];
}

export function collectEphemeralMessages(messages: ChatMsg[]): ChatMsg[] {
  return messages.filter((m) => m.role === 'heartbeat');
}

/**
 * Índice donde insertar heartbeats del turno actual.
 * Siempre antes del assistant del turno — nunca al final si ya hay respuesta
 * (si no, Tool Usage queda flotando entre el último mensaje y el composer).
 */
export function findHeartbeatInsertIndex(messages: ChatMsg[]): number {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i]?.role === 'assistant' && messages[i]?.streaming) {
      return i;
    }
  }
  let lastUser = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i]?.role === 'user') {
      lastUser = i;
      break;
    }
  }
  if (lastUser >= 0) {
    for (let i = lastUser + 1; i < messages.length; i++) {
      if (messages[i]?.role === 'assistant') return i;
    }
  }
  return messages.length;
}

/**
 * Si quedaron tool heartbeats *después* del assistant del último turno
 * (p. ej. eventos SSE tardíos antes del fix, o race al cerrar streaming),
 * los mueve justo antes de ese assistant para que Tool Usage no flote
 * entre la respuesta y el composer.
 */
export function coalesceTrailingToolHeartbeats(messages: ChatMsg[]): ChatMsg[] {
  let lastUser = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i]?.role === 'user') {
      lastUser = i;
      break;
    }
  }
  if (lastUser < 0) return messages;

  let assistantIdx = -1;
  for (let i = lastUser + 1; i < messages.length; i++) {
    if (messages[i]?.role === 'assistant') {
      assistantIdx = i;
      break;
    }
  }
  if (assistantIdx < 0) return messages;

  const trailingIdx: number[] = [];
  for (let i = assistantIdx + 1; i < messages.length; i++) {
    const m = messages[i];
    if (m?.role === 'user' || m?.role === 'assistant') break;
    if (m?.role === 'heartbeat' && m.heartbeatKind === 'tool') {
      trailingIdx.push(i);
    }
  }
  if (!trailingIdx.length) return messages;

  const trailing = trailingIdx.map((i) => messages[i]);
  const without = messages.filter((_, i) => !trailingIdx.includes(i));
  let newAssistant = -1;
  for (let i = lastUser + 1; i < without.length; i++) {
    if (without[i]?.role === 'assistant') {
      newAssistant = i;
      break;
    }
  }
  if (newAssistant < 0) return messages;
  const out = [...without];
  out.splice(newAssistant, 0, ...trailing);
  return out;
}

/** True si hay heartbeat de herramienta en el turno actual (entre último user y assistant streaming). */
export function hasToolHeartbeatInCurrentTurn(messages: ChatMsg[]): boolean {
  const insertAt = findHeartbeatInsertIndex(messages);
  const end =
    insertAt < messages.length && messages[insertAt]?.role === 'assistant'
      ? insertAt
      : messages.length;
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

/** Stale PROGRESO box from a failed manifest load (kept in sessionStorage). */
export function isCatalogMissHeartbeat(m: ChatMsg | undefined): boolean {
  if (m?.role !== 'heartbeat') return false;
  return /not found in catalog for tenant/i.test((m.text || '').trim());
}

/** Remove stale "Pensando…" / catalog-miss status heartbeats from persisted chat history. */
export function stripThinkingStatusHeartbeats(messages: ChatMsg[]): ChatMsg[] {
  return messages.filter((m) => !isThinkingStatusHeartbeat(m) && !isCatalogMissHeartbeat(m));
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
  context_token_breakdown?: Record<string, number> | null;
};

/** Header mirrors gateway log line: last turn usage_tokens, not session sum. */
export function applyLastTurnTokenDisplay(
  setLastTurnUsage: (value: UsageTokenBreakdown | null) => void,
  setContextEstimatedTokens: (value: number | null) => void,
  meta: TurnTokenMeta,
  setContextTokenBreakdown?: (value: ContextTokenBreakdown | null) => void
): void {
  const usage = normalizeUsageTokens(meta.usage_tokens);
  const breakdown = normalizeContextTokenBreakdown(meta.context_token_breakdown ?? null);
  if (usage) {
    setLastTurnUsage(usage);
  } else {
    setLastTurnUsage(null);
  }
  if (breakdown) {
    setContextTokenBreakdown?.(breakdown);
    setContextEstimatedTokens(breakdown.total);
    return;
  }
  setContextTokenBreakdown?.(null);
  const ctx = meta.context_estimated_tokens;
  if (ctx != null && Number.isFinite(ctx) && ctx >= 0) {
    setContextEstimatedTokens(Math.floor(ctx));
    return;
  }
  // Prefer billed input_tokens as occupancy when no heuristic breakdown arrived.
  if (usage && usage.input_tokens > 0) {
    setContextEstimatedTokens(usage.input_tokens);
    return;
  }
  setContextEstimatedTokens(null);
}
