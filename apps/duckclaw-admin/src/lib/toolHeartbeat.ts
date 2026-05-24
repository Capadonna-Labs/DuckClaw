/** Utilidades para heartbeats de herramienta en el chat admin. */

import type { ChatMsg, ToolHeartbeatPhase } from '@/components/chat/types';

export type { ToolHeartbeatPhase };

export function parseToolNameFromHeartbeatText(text: string): string | null {
  const m = (text || '').match(/^🔄\s*Usando:\s*(.+?)(?:\s*·|$)/u);
  return m ? m[1].trim() : null;
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

/** Índice del último heartbeat de la misma herramienta antes de ``beforeIndex``. */
export function findToolHeartbeatIndex(
  messages: ChatMsg[],
  toolName: string,
  beforeIndex: number
): number {
  const needle = toolName.trim();
  if (!needle) return -1;
  const end = beforeIndex >= 0 ? beforeIndex : messages.length;
  for (let i = end - 1; i >= 0; i--) {
    const x = messages[i];
    if (x.role !== 'heartbeat' || x.heartbeatKind !== 'tool') continue;
    const name = (x.toolName || parseToolNameFromHeartbeatText(x.text || '')).trim();
    if (name === needle) return i;
  }
  return -1;
}
