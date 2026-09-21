/** Heartbeats de tool desde backlog/activity → ChatMsg (pares start/done). */

import type { ChatMsg } from '@/components/chat/types';
import {
  createToolInvocationId,
  mapSseToolPhase,
  toolHeartbeatDisplayText,
} from '@/lib/toolHeartbeat';

export type ActivityToolEvent = {
  kind?: string;
  text?: string;
  worker_id?: string;
  swarm_slot?: number;
  tool_name?: string;
  tool_phase?: string;
  elapsed_ms?: number;
  turn_user_index?: number;
};

/** Agrupa start→done del mismo tool; evita filas running huérfanas en UI. */
export function toolHeartbeatsFromActivity(
  events: ActivityToolEvent[],
  activeWorker: string,
  turnUserIndex?: number
): ChatMsg[] {
  const out: ChatMsg[] = [];
  const runningByTool = new Map<string, number>();
  for (const ev of events) {
    const toolName = String(ev.tool_name || '').trim();
    if (ev.kind !== 'tool' || !toolName) continue;
    const phase = mapSseToolPhase(ev.tool_phase as 'start' | 'done' | 'error' | undefined);
    const elapsedMs =
      ev.elapsed_ms != null && Number.isFinite(Number(ev.elapsed_ms))
        ? Number(ev.elapsed_ms)
        : undefined;
    const isStart = phase === 'running';
    const runningIdx = runningByTool.get(toolName);
    const startedAt = elapsedMs != null ? Date.now() - elapsedMs : Date.now();
    const turnIdx =
      turnUserIndex != null && Number.isFinite(turnUserIndex)
        ? turnUserIndex
        : ev.turn_user_index != null && Number.isFinite(Number(ev.turn_user_index))
          ? Math.max(1, Math.floor(Number(ev.turn_user_index)))
          : undefined;
    const base: ChatMsg = {
      role: 'heartbeat',
      text: toolHeartbeatDisplayText(toolName, phase, elapsedMs),
      heartbeatKind: 'tool',
      workerId: String(ev.worker_id || activeWorker || ''),
      swarmSlot:
        ev.swarm_slot != null && Number.isFinite(Number(ev.swarm_slot))
          ? Math.max(1, Math.floor(Number(ev.swarm_slot)))
          : 1,
      toolName,
      toolInvocationId: createToolInvocationId(toolName),
      toolPhase: phase ?? 'done',
      toolStartedAt: startedAt,
      toolElapsedMs: elapsedMs,
      turnUserIndex: turnIdx,
    };
    if (isStart) {
      runningByTool.set(toolName, out.length);
      out.push(base);
      continue;
    }
    if (runningIdx != null && out[runningIdx]) {
      out[runningIdx] = {
        ...base,
        toolInvocationId: out[runningIdx].toolInvocationId,
        toolStartedAt: out[runningIdx].toolStartedAt,
      };
      runningByTool.delete(toolName);
      continue;
    }
    out.push(base);
  }
  return out;
}
