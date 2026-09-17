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

/**
 * Una caja Tool Usage por turno (entre user y el siguiente user/fin).
 * Heartbeats status/plan intercalados no parten el grupo — evita cajas acumuladas.
 */
export function groupMessagesForDisplay(messages: ChatMsg[]): ChatDisplayItem[] {
  const out: ChatDisplayItem[] = [];
  let i = 0;
  while (i < messages.length) {
    const m = messages[i];
    if (m?.role === 'user') {
      out.push({ kind: 'message', index: i });
      i += 1;
      // Recolectar tools del turno; emitir el grupo en el primer tool.
      const turnTools: number[] = [];
      let firstToolOutIdx = -1;
      while (i < messages.length && messages[i]?.role !== 'user') {
        if (isToolHeartbeatMessage(messages[i])) {
          if (firstToolOutIdx < 0) {
            firstToolOutIdx = out.length;
            out.push({ kind: 'toolGroup', indices: turnTools });
          }
          turnTools.push(i);
          i += 1;
          continue;
        }
        out.push({ kind: 'message', index: i });
        i += 1;
      }
      continue;
    }
    if (isToolHeartbeatMessage(m)) {
      // Orphan tools (sin user previo): agrupar consecutivos.
      const indices: number[] = [i];
      i += 1;
      while (i < messages.length && isToolHeartbeatMessage(messages[i])) {
        indices.push(i);
        i += 1;
      }
      out.push({ kind: 'toolGroup', indices });
      continue;
    }
    out.push({ kind: 'message', index: i });
    i += 1;
  }
  return out;
}

export function toolGroupHasRunning(messages: ChatMsg[], indices: number[]): boolean {
  return indices.some((idx) => isToolHeartbeatRunning(messages[idx]));
}

/**
 * Duración de pared del bloque (primer start → último end), no suma de
 * elapsed por tool — si no 165×3s → "9m" engañoso.
 */
export function toolGroupTotalElapsedMs(messages: ChatMsg[], indices: number[]): number | null {
  let minStart: number | null = null;
  let maxEnd: number | null = null;
  let maxElapsed = 0;
  let anyElapsed = false;
  for (const idx of indices) {
    const m = messages[idx];
    if (isToolHeartbeatRunning(m)) return null;
    const start = m.toolStartedAt;
    const elapsed =
      m.toolElapsedMs ??
      (start != null ? Math.max(0, Date.now() - start) : undefined);
    if (elapsed != null && Number.isFinite(elapsed)) {
      anyElapsed = true;
      maxElapsed = Math.max(maxElapsed, elapsed);
      if (start != null && Number.isFinite(start)) {
        minStart = minStart == null ? start : Math.min(minStart, start);
        const end = start + elapsed;
        maxEnd = maxEnd == null ? end : Math.max(maxEnd, end);
      }
    } else if (start != null && Number.isFinite(start)) {
      minStart = minStart == null ? start : Math.min(minStart, start);
      maxEnd = maxEnd == null ? start : Math.max(maxEnd, start);
    }
  }
  if (minStart != null && maxEnd != null && maxEnd >= minStart) {
    return Math.max(0, maxEnd - minStart);
  }
  // Sin timestamps de inicio: mostrar el max individual, nunca la suma.
  return anyElapsed ? maxElapsed : null;
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

export interface GroupedToolInvocation {
  toolName: string;
  count: number;
  /** Tiempo de la invocación más reciente (completada). */
  latestMs: number | null;
  /** Máximo entre invocaciones completadas del mismo tool. */
  maxMs: number | null;
  averageMs: number | null;
  isRunning: boolean;
  isError: boolean;
  messages: ChatMsg[];
}

/** Agrupa herramientas repetidas del mismo tipo, mostrando contador y promedios. */
export function groupToolInvocationsByName(
  messages: ChatMsg[],
  indices: number[]
): GroupedToolInvocation[] {
  const items = indices.map((i) => messages[i]).filter(isToolHeartbeatMessage);
  
  // Agrupar por nombre de herramienta
  const grouped = new Map<string, ChatMsg[]>();
  for (const msg of items) {
    const name = toolDisplayName(msg);
    const existing = grouped.get(name) || [];
    existing.push(msg);
    grouped.set(name, existing);
  }
  
  // Convertir a formato de salida con estadísticas
  const result: GroupedToolInvocation[] = [];
  for (const [toolName, toolMessages] of grouped.entries()) {
    const count = toolMessages.length;
    const hasRunning = toolMessages.some((m) => isToolHeartbeatRunning(m));
    const hasError = toolMessages.some((m) => m.toolPhase === 'error');
    
    // Calcular tiempos solo de mensajes completados
    const completedMessages = toolMessages.filter((m) => !isToolHeartbeatRunning(m));
    const times = completedMessages
      .map((m) => {
        const ms =
          m.toolElapsedMs ??
          (m.toolStartedAt != null ? Math.max(0, Date.now() - m.toolStartedAt) : undefined);
        return ms != null && Number.isFinite(ms) ? ms : null;
      })
      .filter((t): t is number => t !== null);
    
    // Último tiempo (del mensaje más reciente)
    const newestCompleted = newestByStartedAt(completedMessages);
    const latestMs =
      newestCompleted?.toolElapsedMs ??
      (newestCompleted?.toolStartedAt != null
        ? Math.max(0, Date.now() - newestCompleted.toolStartedAt)
        : null);
    
    // Tiempo promedio y máximo
    const averageMs = times.length > 0 ? times.reduce((a, b) => a + b, 0) / times.length : null;
    const maxMs = times.length > 0 ? Math.max(...times) : null;
    
    result.push({
      toolName,
      count,
      latestMs,
      maxMs,
      averageMs,
      isRunning: hasRunning,
      isError: hasError,
      messages: toolMessages,
    });
  }
  
  return result;
}
