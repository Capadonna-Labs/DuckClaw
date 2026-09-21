'use client';

import { useCallback, useEffect, useMemo, useRef, type Dispatch, type MutableRefObject, type SetStateAction } from 'react';

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
  writeEphemeralHeartbeats,
} from '@/lib/chatEphemeralStorage';
import { isConversationNotFoundError } from '@/lib/adminErrors';
import { writeStoredVaultPath } from '@/lib/conversationVaultStorage';
import { readPendingDetachedTurn } from '@/lib/detachedTurnState';
import { workerOptionIds, workersInclude } from '@/lib/workerOptions';
import { useVisibilityAwareInterval } from '@/hooks/useVisibilityAwareInterval';

import {
  collectEphemeralMessages,
  conversationHasLoopResult,
  conversationIndicatesLoopScheduling,
  isLoopProgressHeartbeat,
  mergeHistoryWithEphemeral,
  preserveInFlightOptimisticTurn,
  stripThinkingStatusHeartbeats,
} from './adminChatPure';
import {
  createToolInvocationId,
  finalizeRunningToolHeartbeats,
  mapSseToolPhase,
  toolHeartbeatDisplayText,
} from '@/lib/toolHeartbeat';

type PlaygroundConfig = Awaited<ReturnType<typeof adminService.getPlaygroundConfig>>;

function persistentMessageCount(messages: ChatMsg[]): number {
  return messages.filter((m) => m.role === 'user' || m.role === 'assistant' || m.role === 'error')
    .length;
}

type ActivityEvent = Awaited<
  ReturnType<typeof adminService.getPlaygroundChatActivity>
>['events'][number];

function toolHeartbeatsFromActivity(
  events: ActivityEvent[],
  activeWorker: string
): ChatMsg[] {
  const out: ChatMsg[] = [];
  const runningByTool = new Map<string, number>();
  for (const ev of events) {
    const toolName = String(ev.tool_name || '').trim();
    if (ev.kind !== 'tool' || !toolName) continue;
    const phase = mapSseToolPhase(ev.tool_phase);
    const elapsedMs =
      ev.elapsed_ms != null && Number.isFinite(Number(ev.elapsed_ms))
        ? Number(ev.elapsed_ms)
        : undefined;
    const isStart = phase === 'running';
    const runningIdx = runningByTool.get(toolName);
    const startedAt =
      elapsedMs != null ? Date.now() - elapsedMs : Date.now();
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
      turnUserIndex:
        ev.turn_user_index != null && Number.isFinite(Number(ev.turn_user_index))
          ? Math.max(1, Math.floor(Number(ev.turn_user_index)))
          : undefined,
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

export type UseAdminChatHistoryOptions = {
  enabled: boolean;
  chatId: string;
  config: PlaygroundConfig | null;
  workerId: string;
  initialWorker: string;
  pinnedWorker: string;
  messages: ChatMsg[];
  loopSchedulePolling: boolean;
  loadingRef: MutableRefObject<boolean>;
  setMessages: Dispatch<SetStateAction<ChatMsg[]>>;
  /** Debe ser identidad estable (useCallback). Un wrapper inline causa bucle de GET. */
  setWorkerId: (next: string) => void;
  setVaultPathState: Dispatch<SetStateAction<string>>;
  setHistoryLoading: Dispatch<SetStateAction<boolean>>;
  /** Conversación borrada/404: el contenedor debe limpiar sessionId y re-bootstrap. */
  onConversationNotFound?: () => void;
};

export function useAdminChatHistory({
  enabled,
  chatId,
  config,
  workerId,
  initialWorker,
  pinnedWorker,
  messages,
  loopSchedulePolling,
  loadingRef,
  setMessages,
  setWorkerId,
  setVaultPathState,
  setHistoryLoading,
  onConversationNotFound,
}: UseAdminChatHistoryOptions) {
  const loopHistoryReloadRef = useRef<number[]>([]);
  const historyTenantId = (config?.effective_tenant_id || 'default').trim() || 'default';
  const configReady = config !== null;
  const configRef = useRef(config);
  configRef.current = config;
  const setWorkerIdRef = useRef(setWorkerId);
  setWorkerIdRef.current = setWorkerId;
  const workerIdRef = useRef(workerId);
  workerIdRef.current = workerId;
  const initialWorkerRef = useRef(initialWorker);
  initialWorkerRef.current = initialWorker;
  const pinnedWorkerRef = useRef(pinnedWorker);
  pinnedWorkerRef.current = pinnedWorker;
  const onConversationNotFoundRef = useRef(onConversationNotFound);
  onConversationNotFoundRef.current = onConversationNotFound;
  /** Evita re-GET del mismo hilo si deps colaterales re-disparan el effect. */
  const loadedKeyRef = useRef('');
  const missingNotifiedRef = useRef('');

  const clearLoopHistoryReload = useCallback(() => {
    loopHistoryReloadRef.current.forEach((id) => window.clearTimeout(id));
    loopHistoryReloadRef.current = [];
  }, []);

  const notifyConversationMissing = useCallback((session: string) => {
    if (!session || missingNotifiedRef.current === session) return;
    missingNotifiedRef.current = session;
    loadedKeyRef.current = '';
    onConversationNotFoundRef.current?.();
  }, []);

  const reloadHistory = useCallback((opts?: { force?: boolean }) => {
    if (!enabled || !chatId || configRef.current === null) return;
    // Nunca mezclar Redis + ephemeral mientras hay turno SSE activo (evita cuadros duplicados).
    if (loadingRef.current) return;
    setHistoryLoading(true);
    Promise.all([
      adminService.getConversation(chatId, historyTenantId),
      adminService.getPlaygroundChatActivity(chatId, 80).catch(() => ({ events: [] })),
    ])
      .then(([data, activity]) => {
        if (loadingRef.current) return;
        const fromServer = historyToChatMessages(data.messages, historyTenantId);
        const hasLoopResult = conversationHasLoopResult(fromServer);
        if (hasLoopResult) {
          clearLoopHistoryReload();
        }
        const activeWorker =
          workerIdRef.current || initialWorkerRef.current || '';
        const storedEphemeral = readEphemeralHeartbeats(chatId, activeWorker);
        const activityEphemeral = toolHeartbeatsFromActivity(
          activity.events || [],
          activeWorker
        );
        setMessages((prev) => {
          if (persistentMessageCount(prev) > persistentMessageCount(fromServer)) {
            return prev;
          }
          const liveEphemeral = filterEphemeralForWorker(
            collectEphemeralMessages(prev),
            activeWorker
          );
          let ephemeral = mergeEphemeralHeartbeats(
            mergeEphemeralHeartbeats(storedEphemeral, liveEphemeral),
            activityEphemeral
          );
          if (hasLoopResult) {
            ephemeral = ephemeral.filter(
              (m) =>
                !(
                  m.role === 'heartbeat' &&
                  isLoopProgressHeartbeat(m.text || '')
                )
            );
          }
          const pendingText = readPendingDetachedTurn(chatId)?.text;
          const mergedServer = preserveInFlightOptimisticTurn(
            fromServer,
            prev,
            pendingText
          );
          const withImages = preserveImagePreviewsFromPrevious(mergedServer, prev);
          return stripThinkingStatusHeartbeats(
            finalizeRunningToolHeartbeats(
              mergeHistoryWithEphemeral(withImages, ephemeral)
            )
          );
        });
      })
      .catch((err) => {
        if (isConversationNotFoundError(err)) notifyConversationMissing(chatId);
      })
      .finally(() => setHistoryLoading(false));
  }, [
    chatId,
    clearLoopHistoryReload,
    enabled,
    historyTenantId,
    loadingRef,
    notifyConversationMissing,
    setHistoryLoading,
    setMessages,
  ]);

  const loopPollingActive = useMemo(
    () => loopSchedulePolling || conversationIndicatesLoopScheduling(messages),
    [loopSchedulePolling, messages]
  );

  useVisibilityAwareInterval(() => {
    if (!enabled || !chatId || loadingRef.current || configRef.current === null) return;
    reloadHistory({ force: true });
  }, loopPollingActive && enabled ? 30_000 : null);

  useEffect(() => {
    return () => {
      loopHistoryReloadRef.current.forEach((id) => window.clearTimeout(id));
      loopHistoryReloadRef.current = [];
    };
  }, []);

  const scheduleLoopHistoryReload = useCallback((opts?: { extended?: boolean }) => {
    clearLoopHistoryReload();
    reloadHistory({ force: true });
    const delays = opts?.extended
      ? [3_000, 8_000, 15_000, 30_000, 60_000, 120_000, 180_000, 240_000]
      : [3_000, 8_000, 15_000, 30_000, 60_000];
    loopHistoryReloadRef.current = delays.map((ms) =>
      window.setTimeout(() => {
        reloadHistory({ force: true });
      }, ms)
    );
  }, [clearLoopHistoryReload, reloadHistory]);

  // Reset del candado solo cuando cambia el chat (antes del load effect).
  // ponytail: si no se limpia `messages` aquí, un GET fallido/lento para el chat
  // nuevo (p. ej. 503 transitorio justo tras crear la conversación, mientras el
  // write async de creación aún no aterriza) deja visible el historial/heartbeats
  // del chat ANTERIOR bajo el título del chat nuevo — confirmado en vivo.
  const prevChatIdRef = useRef(chatId);
  if (prevChatIdRef.current !== chatId) {
    prevChatIdRef.current = chatId;
    loadedKeyRef.current = '';
    setMessages([]);
  }

  useEffect(() => {
    if (!enabled || !chatId || !configReady) {
      return;
    }

    const loadKey = `${chatId}|${historyTenantId}`;
    if (loadedKeyRef.current === loadKey) return;
    if (loadingRef.current) return;

    loadedKeyRef.current = loadKey;
    setHistoryLoading(true);
    let cancelled = false;
    const workerAtLoad = workerIdRef.current || initialWorkerRef.current || '';
    const workers = configRef.current?.workers;
    const pinned = pinnedWorkerRef.current;

    Promise.all([
      adminService.getConversation(chatId, historyTenantId),
      adminService.getPlaygroundChatActivity(chatId, 80).catch(() => ({ events: [] })),
    ])
      .then(([data, activity]) => {
        if (cancelled || loadingRef.current) return;
        const fromServer = historyToChatMessages(data.messages, historyTenantId);
        const storedEphemeral = readEphemeralHeartbeats(chatId, workerAtLoad);
        const activityEphemeral = toolHeartbeatsFromActivity(
          activity.events || [],
          workerAtLoad
        );
        setMessages((prev) => {
          if (persistentMessageCount(prev) > persistentMessageCount(fromServer)) {
            loadedKeyRef.current = '';
            return prev;
          }
          const liveEphemeral = filterEphemeralForWorker(
            collectEphemeralMessages(prev),
            workerAtLoad
          );
          let ephemeral = mergeEphemeralHeartbeats(
            mergeEphemeralHeartbeats(storedEphemeral, liveEphemeral),
            activityEphemeral
          );
          const hasLoopResult = conversationHasLoopResult(fromServer);
          if (hasLoopResult) {
            ephemeral = ephemeral.filter(
              (m) =>
                !(
                  m.role === 'heartbeat' &&
                  isLoopProgressHeartbeat(m.text || '')
                )
            );
          }
          const pendingText = readPendingDetachedTurn(chatId)?.text;
          const mergedServer = preserveInFlightOptimisticTurn(
            fromServer,
            prev,
            pendingText
          );
          const withImages = preserveImagePreviewsFromPrevious(mergedServer, prev);
          return stripThinkingStatusHeartbeats(
            finalizeRunningToolHeartbeats(
              mergeHistoryWithEphemeral(withImages, ephemeral)
            )
          );
        });
        const convWorker = (
          data.preferred_worker_id ||
          data.last_worker_id ||
          ''
        ).trim();
        if (pinned && workersInclude(workers, pinned)) {
          setWorkerIdRef.current(pinned);
        } else if (convWorker && workersInclude(workers, convWorker)) {
          setWorkerIdRef.current(convWorker);
        } else if (!workerIdRef.current) {
          if (workersInclude(workers, 'default')) {
            setWorkerIdRef.current('default');
          } else {
            const ids = workerOptionIds(workers);
            if (ids[0]) setWorkerIdRef.current(ids[0]);
          }
        }
        const convVault = (data.vault_db_path || '').trim();
        if (convVault) {
          setVaultPathState(convVault);
          writeStoredVaultPath(chatId, convVault);
        }
      })
      .catch((err) => {
        if (isConversationNotFoundError(err)) {
          notifyConversationMissing(chatId);
          return;
        }
        // ponytail: justo tras crear una conversación, el GET puede llegar antes de
        // que el write async de creación aterrice (503 transitorio) — un solo
        // reintento corto cubre esa carrera sin loop de retries.
        window.setTimeout(() => {
          if (!cancelled) reloadHistory({ force: true });
        }, 800);
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [
    chatId,
    configReady,
    enabled,
    historyTenantId,
    loadingRef,
    setHistoryLoading,
    setMessages,
    setVaultPathState,
  ]);

  useEffect(() => {
    if (!chatId) return;
    writeEphemeralHeartbeats(chatId, workerId, messages);
  }, [chatId, workerId, messages]);

  return {
    reloadHistory,
    scheduleLoopHistoryReload,
    clearLoopHistoryReload,
  };
}
