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
import { workerOptionIds, workersInclude } from '@/lib/workerOptions';
import { useVisibilityAwareInterval } from '@/hooks/useVisibilityAwareInterval';

import {
  collectEphemeralMessages,
  conversationHasLoopResult,
  conversationIndicatesLoopScheduling,
  isLoopProgressHeartbeat,
  mergeHistoryWithEphemeral,
} from './adminChatPure';
import { finalizeRunningToolHeartbeats } from '@/lib/toolHeartbeat';

type PlaygroundConfig = Awaited<ReturnType<typeof adminService.getPlaygroundConfig>>;

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
    adminService
      .getConversation(chatId, historyTenantId)
      .then((data) => {
        if (loadingRef.current) return;
        const fromServer = historyToChatMessages(data.messages, historyTenantId);
        const hasLoopResult = conversationHasLoopResult(fromServer);
        if (hasLoopResult) {
          clearLoopHistoryReload();
        }
        const activeWorker =
          workerIdRef.current || initialWorkerRef.current || '';
        const storedEphemeral = readEphemeralHeartbeats(chatId, activeWorker);
        setMessages((prev) => {
          const liveEphemeral = filterEphemeralForWorker(
            collectEphemeralMessages(prev),
            activeWorker
          );
          let ephemeral = mergeEphemeralHeartbeats(storedEphemeral, liveEphemeral);
          if (hasLoopResult) {
            ephemeral = ephemeral.filter(
              (m) =>
                !(
                  m.role === 'heartbeat' &&
                  isLoopProgressHeartbeat(m.text || '')
                )
            );
          }
          const withImages = preserveImagePreviewsFromPrevious(fromServer, prev);
          return finalizeRunningToolHeartbeats(
            mergeHistoryWithEphemeral(withImages, ephemeral)
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

  const scheduleLoopHistoryReload = useCallback(() => {
    clearLoopHistoryReload();
    reloadHistory({ force: true });
    const delays = [3_000, 8_000, 15_000, 30_000, 60_000];
    loopHistoryReloadRef.current = delays.map((ms) =>
      window.setTimeout(() => {
        reloadHistory({ force: true });
      }, ms)
    );
  }, [clearLoopHistoryReload, reloadHistory]);

  // Reset del candado solo cuando cambia el chat (antes del load effect).
  const prevChatIdRef = useRef(chatId);
  if (prevChatIdRef.current !== chatId) {
    prevChatIdRef.current = chatId;
    loadedKeyRef.current = '';
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

    adminService
      .getConversation(chatId, historyTenantId)
      .then((data) => {
        if (cancelled || loadingRef.current) return;
        const fromServer = historyToChatMessages(data.messages, historyTenantId);
        const storedEphemeral = readEphemeralHeartbeats(chatId, workerAtLoad);
        setMessages((prev) => {
          const liveEphemeral = filterEphemeralForWorker(
            collectEphemeralMessages(prev),
            workerAtLoad
          );
          let ephemeral = mergeEphemeralHeartbeats(storedEphemeral, liveEphemeral);
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
          const withImages = preserveImagePreviewsFromPrevious(fromServer, prev);
          return finalizeRunningToolHeartbeats(
            mergeHistoryWithEphemeral(withImages, ephemeral)
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
        if (isConversationNotFoundError(err)) notifyConversationMissing(chatId);
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
