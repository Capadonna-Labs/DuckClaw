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
import { toolHeartbeatsFromActivity } from '@/lib/chatActivityHeartbeats';
import { finalizeRunningToolHeartbeats } from '@/lib/toolHeartbeat';
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
    setLoading(true);
    setThinking(false);

    const applyActivity = () => {
      void adminService
        .getPlaygroundChatActivity(chatId, 80)
        .then((data) => {
          if (cancelled) return;
          const heartbeats = toolHeartbeatsFromActivity(
            data.events || [],
            activeWorker
          );
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
            // Reemplazar tools del turno (no apilar start sin done).
            const before = next.slice(0, userIdx == null ? next.length : userIdx + 1);
            const afterUser = next.slice(userIdx == null ? next.length : userIdx + 1);
            const nonTools = afterUser.filter(
              (m) => !(m.role === 'heartbeat' && m.heartbeatKind === 'tool')
            );
            return coalesceTrailingToolHeartbeats([
              ...before,
              ...heartbeats,
              ...nonTools,
            ]);
          });
        })
        .catch(() => undefined);
    };

    const finishFromHistory = (fromServer: ChatMsg[]) => {
      setMessages((prev) => {
        const ephemeral = mergeEphemeralHeartbeats(
          readEphemeralHeartbeats(chatId, activeWorker),
          filterEphemeralForWorker(collectEphemeralMessages(prev), activeWorker)
        );
        const withImages = preserveImagePreviewsFromPrevious(fromServer, prev);
        return stripThinkingStatusHeartbeats(
          finalizeRunningToolHeartbeats(mergeHistoryWithEphemeral(withImages, ephemeral))
        );
      });
      clearPendingDetachedTurn(chatId);
      setLoading(false);
      setThinking(false);
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
          finishFromHistory(fromServer);
        })
        .catch(() => undefined);
    };

    const forceRelease = () => {
      if (cancelled) return;
      void adminService
        .getConversation(chatId, tenantId)
        .then((data) => {
          if (cancelled) return;
          const fromServer = historyToChatMessages(data.messages, tenantId);
          finishFromHistory(fromServer.length ? fromServer : []);
        })
        .catch(() => {
          if (cancelled) return;
          setMessages((m) =>
            coalesceTrailingToolHeartbeats(
              finalizeRunningToolHeartbeats(stripThinkingStatusHeartbeats(m))
            )
          );
          clearPendingDetachedTurn(chatId);
          setLoading(false);
          setThinking(false);
        });
    };

    const delays = [
      500, 2_000, 5_000, 10_000, 20_000, 35_000, 60_000, 90_000, 120_000, 180_000, 240_000, 300_000,
    ];
    const timers = delays.flatMap((delay) => [
      window.setTimeout(applyActivity, delay),
      window.setTimeout(checkCompletion, delay + 250),
    ]);
    timers.push(window.setTimeout(forceRelease, 310_000));
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
