/** Utilidades para heartbeats de herramienta en el chat admin. */

import type { ChatMsg, ToolHeartbeatPhase } from '@/components/chat/types';

export type { ToolHeartbeatPhase };

let _invocationSeq = 0;

export function createToolInvocationId(toolName: string): string {
  _invocationSeq += 1;
  const slug = (toolName || 'tool').trim().replace(/\s+/g, '_') || 'tool';
  return `${slug}-${Date.now()}-${_invocationSeq}`;
}

export function toolHeartbeatInvocationKey(m: ChatMsg): string | null {
  if (m.role !== 'heartbeat' || m.heartbeatKind !== 'tool') return null;
  const id = (m.toolInvocationId || '').trim();
  if (id) return id;
  const name = (m.toolName || parseToolNameFromHeartbeatText(m.text || '') || '').trim();
  if (!name) return null;
  if (m.toolStartedAt != null) return `${name}@${m.toolStartedAt}`;
  return `${name}@${m.text || ''}`;
}

export function parseToolNameFromHeartbeatText(text: string): string | null {
  const raw = (text || '').trim();
  if (!raw) return null;
  const using = raw.match(/🔄\s*Usando:\s*(.+?)(?:\s*·|$)/);
  if (using) return using[1].trim();
  const legacy = raw.match(/herramienta\s+([A-Za-z0-9_.-]+)/i);
  return legacy ? legacy[1].trim() : null;
}

export function formatToolDurationMs(ms: number | null | undefined): string {
  if (ms == null || !Number.isFinite(ms)) return '';
  const n = Math.max(0, ms);
  if (n < 1000) return `⏱️ ${Math.round(n)}ms`;
  const sec = n / 1000;
  if (sec < 60) return `⏱️ ${sec.toFixed(2)}s`;
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `⏱️ ${m}m ${s}s`;
}

export function toolHeartbeatDisplayText(
  toolName: string,
  phase: ToolHeartbeatPhase | 'running' | undefined,
  elapsedMs: number | null | undefined
): string {
  const name = (toolName || 'tool').trim();
  const base = `🔄 Usando: ${name}`;
  if (phase === 'error') {
    const dur = formatToolDurationMs(elapsedMs);
    return dur ? `${base} · error · ${dur}` : `${base} · error`;
  }
  const dur = formatToolDurationMs(elapsedMs);
  return dur ? `${base} · ${dur}` : base;
}

export function mapSseToolPhase(
  phase: 'start' | 'done' | 'error' | undefined
): ToolHeartbeatPhase | 'running' | undefined {
  if (phase === 'start') return 'running';
  return phase;
}

export function isToolHeartbeatRunning(m: ChatMsg): boolean {
  if (m.role !== 'heartbeat' || m.heartbeatKind !== 'tool') return false;
  const phase = m.toolPhase;
  return (
    phase === 'running' ||
    phase === 'start' ||
    (phase !== 'done' && phase !== 'error')
  );
}

/** Cierra cronómetros de herramienta que quedaron en curso (p. ej. done SSE antes que start). */
export function finalizeRunningToolHeartbeats(messages: ChatMsg[]): ChatMsg[] {
  const now = Date.now();
  let changed = false;
  const next = messages.map((msg) => {
    if (!isToolHeartbeatRunning(msg)) return msg;
    changed = true;
    const elapsed =
      msg.toolElapsedMs ??
      (msg.toolStartedAt != null ? Math.max(0, now - msg.toolStartedAt) : undefined);
    return {
      ...msg,
      toolPhase: 'done' as const,
      toolElapsedMs: elapsed,
      text: toolHeartbeatDisplayText(
        (msg.toolName || parseToolNameFromHeartbeatText(msg.text || '') || 'tool').trim(),
        'done',
        elapsed
      ),
    };
  });
  return changed ? next : messages;
}

/** Índice del último heartbeat en curso de la misma herramienta antes de ``beforeIndex``. */
export function findRunningToolHeartbeatIndex(
  messages: ChatMsg[],
  toolName: string,
  beforeIndex: number
): number {
  const needle = toolName.trim();
  if (!needle) return -1;
  const end = beforeIndex >= 0 ? beforeIndex : messages.length;
  for (let i = end - 1; i >= 0; i--) {
    const x = messages[i];
    if (!isToolHeartbeatRunning(x)) continue;
    const name = (x.toolName || parseToolNameFromHeartbeatText(x.text || '') || '').trim();
    if (name === needle) return i;
  }
  return -1;
}

/** @deprecated Prefer findRunningToolHeartbeatIndex for done/error; kept for legacy callers. */
export function findToolHeartbeatIndex(
  messages: ChatMsg[],
  toolName: string,
  beforeIndex: number
): number {
  return findRunningToolHeartbeatIndex(messages, toolName, beforeIndex);
}
