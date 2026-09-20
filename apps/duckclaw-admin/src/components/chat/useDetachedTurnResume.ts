'use client';

import { useEffect, useRef, type Dispatch, type SetStateAction } from 'react';
import { adminService } from '@/services/adminService';
import type { ChatMsg } from '@/components/chat/types';
import {
  historyToChatMessages,
  preserveImagePreviewsFromPrevious,
} from '@/lib/chatMessageImages';
import {
  filterEphemeralForWorker,
  mergeEphemeralHeartbeats,
  readEphemeralHeartbeats,
} from '@/lib/chatEphemeralStorage';
import {
  createToolInvocationId,
  finalizeRunningToolHeartbeats,
  mapSseToolPhase,
  toolHeartbeatDisplayText,
} from '@/lib/toolHeartbeat';
import {
  clearPendingDetachedTurn,
  readPendingDetachedTurn,
} from '@/lib/detachedTurnState';
import {
  coalesceTrailingToolHeartbeats,
  collectEphemeralMessages,
  mergeHistoryWithEphemeral,
  stripThinkingStatusHeartbeats,
} from './adminChatPure';

type ResumeConfig = {
  effective_tenant_id?: string;
};

/** Reopen PWA mid-detached-turn: restore loading, poll activity, clear pending when done. */
export function useDetachedTurnResume(opts: {
  enabled: boolean;
  chatId: string;
  config: ResumeConfig | null;
  workerId: string;
  initialWorker: string;
  setMessages: Dispatch<SetStateAction<ChatMsg[]>>;
  setLoading: (v: boolean) => void;
  setThinking: (v: boolean) => void;
}): void {
  const { enabled, chatId, config, workerId, initialWorker, setMessages, setLoading, setThinking } =
    opts;
  const resumedDetachedRef = useRef('');

  useEffect(() => {
    if (!enabled || !chatId || !config) return;
    const pending = readPendingDetachedTurn(chatId);
    if (!pending) return;
    const resumeKey = `${pending.chatId}|${pending.startedAt}`;
    if (resumedDetachedRef.current === resumeKey) return;
    resumedDetachedRef.current = resumeKey;

    let cancelled = false;
    const activeWorker = pending.workerId || workerId || initialWorker || '';
    const tenantId = pending.tenantId || config.effective_tenant_id || 'default';
    const seenActivity = new Set<string>();
    setLoading(true);
    setThinking(false);

    const applyActivity = () => {
      void adminService
        .getPlaygroundChatActivity(chatId, 80)
        .then((data) => {
          if (cancelled) return;
          const heartbeats: ChatMsg[] = [];
          for (const ev of data.events || []) {
            const toolName = String(ev.tool_name || '').trim();
            if (ev.kind !== 'tool' || !toolName) continue;
            const key = [
              ev.worker_id || '',
              toolName,
              ev.tool_phase || '',
              ev.elapsed_ms ?? '',
              ev.text || '',
            ].join('|');
            if (seenActivity.has(key)) continue;
            seenActivity.add(key);
            const phase = mapSseToolPhase(ev.tool_phase);
            const elapsedMs =
              ev.elapsed_ms != null && Number.isFinite(Number(ev.elapsed_ms))
                ? Number(ev.elapsed_ms)
                : undefined;
            const startedAt =
              elapsedMs != null ? Date.now() - elapsedMs : pending.startedAt;
            heartbeats.push({
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
            });
          }
          if (!heartbeats.length) return;
          setMessages((prev) => {
            const next = [...prev];
            const userIdx = [...next]
              .map((m, i) => ({ m, i }))
              .reverse()
              .find(
                ({ m }) =>
                  m.role === 'user' &&
                  (m.text || '').trim() === pending.text.trim()
              )?.i;
            let insertAt = userIdx == null ? next.length : userIdx + 1;
            while (insertAt < next.length && next[insertAt]?.role === 'heartbeat') {
              insertAt += 1;
            }
            next.splice(insertAt, 0, ...heartbeats);
            return coalesceTrailingToolHeartbeats(next);
          });
        })
        .catch(() => undefined);
    };

    const checkCompletion = () => {
      void adminService
        .getConversation(chatId, tenantId)
        .then((data) => {
          if (cancelled) return;
          const fromServer = historyToChatMessages(data.messages, tenantId);
          const userIdx = [...fromServer]
            .map((m, i) => ({ m, i }))
            .reverse()
            .find(
              ({ m }) =>
                m.role === 'user' &&
                (m.text || '').trim() === pending.text.trim()
            )?.i;
          const done =
            userIdx != null &&
            fromServer
              .slice(userIdx + 1)
              .some((m) => m.role === 'assistant' && (m.text || '').trim());
          if (!done) return;
          setMessages((prev) => {
            const ephemeral = mergeEphemeralHeartbeats(
              readEphemeralHeartbeats(chatId, activeWorker),
              filterEphemeralForWorker(collectEphemeralMessages(prev), activeWorker)
            );
            const withImages = preserveImagePreviewsFromPrevious(fromServer, prev);
            return stripThinkingStatusHeartbeats(
              finalizeRunningToolHeartbeats(
                mergeHistoryWithEphemeral(withImages, ephemeral)
              )
            );
          });
          clearPendingDetachedTurn(chatId);
          setLoading(false);
          setThinking(false);
        })
        .catch(() => undefined);
    };

    const delays = [
      500, 2_000, 5_000, 10_000, 20_000, 35_000, 60_000, 90_000, 120_000, 180_000, 240_000, 300_000,
    ];
    const timers = delays.flatMap((delay) => [
      window.setTimeout(applyActivity, delay),
      window.setTimeout(checkCompletion, delay + 250),
    ]);
    return () => {
      cancelled = true;
      timers.forEach((id) => window.clearTimeout(id));
    };
  }, [
    chatId,
    config,
    enabled,
    initialWorker,
    setLoading,
    setMessages,
    setThinking,
    workerId,
  ]);
}
