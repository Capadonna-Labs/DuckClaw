'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { adminService } from '@/services/adminService';
import type { ChatImagePreview, ChatMsg } from '@/components/chat/types';
import {
  historyToChatMessages,
  payloadImagesFromPreviews,
  preserveImagePreviewsFromPrevious,
  userPreviewsFromPayload,
} from '@/lib/chatMessageImages';
import { useChatImageAttachments } from '@/components/chat/useChatImageAttachments';
import { useChatScrollAnchor } from '@/components/chat/useChatScrollAnchor';
import {
  clearEphemeralHeartbeats,
  clearLegacyEphemeralHeartbeats,
  filterEphemeralForWorker,
  mergeEphemeralHeartbeats,
  readEphemeralHeartbeats,
  writeEphemeralHeartbeats,
} from '@/lib/chatEphemeralStorage';
import { workerMatches } from '@/lib/workerOptions';
import {
  readActorDefaultVaultPath,
  readStoredVaultPath,
  writeStoredVaultPath,
} from '@/lib/conversationVaultStorage';
import { workerOptionIds, workersInclude } from '@/lib/workerOptions';
import { useVisibilityAwareInterval } from '@/hooks/useVisibilityAwareInterval';
import { mutationHeaders } from '@/lib/csrfClient';
import { friendlyGatewayError, parseApiErrorDetail } from '@/lib/adminErrors';
import { playTtsAudio, primeAudioPlayback } from '@/lib/playTtsAudio';
import { finalizeRunningToolHeartbeats } from '@/lib/toolHeartbeat';

import {
  collectEphemeralMessages,
  conversationHasLoopResult,
  conversationIndicatesLoopScheduling,
  isLoopProgressHeartbeat,
  mergeHistoryWithEphemeral,
  readStoredChatTokens,
  readStoredWorker,
  revokeMessageImagePreviews,
  stripThinkingStatusHeartbeats,
  workerStorageKey,
} from './adminChatPure';
import { runAdminChatTurn } from './runAdminChatTurn';


export {
  hasToolHeartbeatInCurrentTurn,
  shouldSkipEmptyStreamingAssistant,
  isThinkingStatusHeartbeat,
  stripThinkingStatusHeartbeats,
  conversationHasLoopResult,
  isLoopProgressHeartbeat,
  conversationIndicatesLoopScheduling,
} from './adminChatPure';

export type UseAdminChatOptions = {
  chatId: string;
  initialWorker?: string;
  /** Si se define, no se restaura otro worker desde historial/storage. */
  lockWorker?: string;
  projectId?: string;
  knowledgeScope?: string;
  enabled?: boolean;
  /** Tras cada turno completado (para refrescar inbox). */
  onConversationActivity?: () => void;
  /** Tras heartbeat visual de sandbox con artefactos nuevos. */
  onSandboxArtifacts?: (payload: {
    sandbox_run_id?: string;
    artifact_ids?: string[];
  }) => void;
};

export type AdminChatController = ReturnType<typeof useAdminChat>;

export function useAdminChat({
  chatId,
  initialWorker = '',
  lockWorker = '',
  projectId = '',
  knowledgeScope = '',
  enabled = true,
  onConversationActivity,
  onSandboxArtifacts,
}: UseAdminChatOptions) {
  const pinnedWorker = (lockWorker || '').trim();
  const [config, setConfig] = useState<Awaited<ReturnType<typeof adminService.getPlaygroundConfig>> | null>(
    null
  );
  const [voiceResponseMode, setVoiceResponseModeState] = useState(false);
  const voiceResponseAvailable = Boolean(config?.voice?.available);
  const liveVoiceAvailable = Boolean(config?.realtime_voice?.available);
  const setVoiceResponseMode = useCallback(
    (next: boolean | ((prev: boolean) => boolean)) => {
      setVoiceResponseModeState((prev) => {
        const value = typeof next === 'function' ? next(prev) : next;
        if (value && !voiceResponseAvailable) return false;
        return value;
      });
    },
    [voiceResponseAvailable]
  );
  const [workerId, setWorkerIdState] = useState(() => {
    const stored = readStoredWorker(chatId);
    if (stored) return stored;
    return initialWorker;
  });

  const setWorkerId = useCallback(
    (
      next: string | ((prev: string) => string),
      opts?: { persist?: boolean }
    ) => {
      setWorkerIdState((prev) => {
        const value = typeof next === 'function' ? next(prev) : next;
        if (typeof window !== 'undefined') {
          try {
            sessionStorage.setItem(workerStorageKey(chatId), value);
          } catch {
            /* ignore quota */
          }
        }
        if (opts?.persist && chatId && value.trim()) {
          const tid = (config?.effective_tenant_id || 'default').trim() || 'default';
          void adminService
            .setPlaygroundWorker({
              chat_id: chatId,
              tenant_id: tid,
              worker_id: value.trim(),
            })
            .catch(() => undefined);
        }
        return value;
      });
    },
    [chatId, config?.effective_tenant_id]
  );

  const prevWorkerIdRef = useRef(workerId);
  useEffect(() => {
    const prev = prevWorkerIdRef.current;
    if (prev && workerId && prev !== workerId) {
      clearEphemeralHeartbeats(chatId, prev);
      clearLegacyEphemeralHeartbeats(chatId);
      setMessages((msgs) =>
        msgs.filter(
          (m) =>
            m.role !== 'heartbeat' ||
            !m.workerId ||
            workerMatches(m.workerId, workerId)
        )
      );
    }
    prevWorkerIdRef.current = workerId;
  }, [chatId, workerId]);

  const setVaultPath = useCallback(
    (next: string) => {
      setVaultPathState(next);
      if (chatId) writeStoredVaultPath(chatId, next);
    },
    [chatId]
  );

  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [input, setInput] = useState('');
  const imageAttachments = useChatImageAttachments();
  const [loading, setLoading] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [thinkingIdentity, setThinkingIdentity] = useState<{ workerId: string; swarmSlot: number }>({
    workerId: '',
    swarmSlot: 1,
  });
  const [error, setError] = useState<string | null>(null);
  const [vaultPath, setVaultPathState] = useState('');
  const [sessionTokenTotal, setSessionTokenTotal] = useState(0);
  const [contextTokensEstimated, setContextTokensEstimated] = useState(false);
  const thinkingStartedAt = useRef<number>(0);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const loadingRef = useRef(false);
  const loopHistoryReloadRef = useRef<number[]>([]);
  const [loopSchedulePolling, setLoopSchedulePolling] = useState(false);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  useEffect(() => {
    loadingRef.current = loading;
  }, [loading]);

  useEffect(
    () => () => {
      revokeMessageImagePreviews(messagesRef.current);
    },
    []
  );

  const finalizeCancelledGeneration = useCallback(() => {
    setMessages((m) => {
      const closedTools = finalizeRunningToolHeartbeats(m);
      if (closedTools.length === 0) return closedTools;
      const last = closedTools[closedTools.length - 1];
      if (last?.role !== 'assistant' || !last.streaming) {
        return stripThinkingStatusHeartbeats(closedTools);
      }
      const base = closedTools.slice(0, -1);
      if (last.text.trim()) {
        return stripThinkingStatusHeartbeats([...base, { ...last, streaming: false }]);
      }
      return stripThinkingStatusHeartbeats([
        ...base,
        { role: 'assistant', text: 'Interrumpido', interrupted: true },
      ]);
    });
  }, []);

  const cancelGeneration = useCallback(() => {
    abortControllerRef.current?.abort();
    if (chatId) {
      void adminService.playgroundChatCancel(chatId).catch(() => undefined);
    }
    setLoading(false);
    setThinking(false);
    finalizeCancelledGeneration();
  }, [chatId, finalizeCancelledGeneration]);

  useEffect(() => {
    setSessionTokenTotal(readStoredChatTokens(chatId));
    setContextTokensEstimated(false);
  }, [chatId]);

  const loadConfig = useCallback(() => {
    if (!enabled) return;
    adminService
      .getPlaygroundConfig(chatId ? { chat_id: chatId } : undefined)
      .then((c) => {
        setConfig(c);
        if (!c.voice?.available) {
          setVoiceResponseModeState(false);
        }
        if (c.authorized === false) {
          setError(c.team_hint || 'Usuario Telegram no autorizado en este tenant');
          setWorkerId('');
          return;
        }
        setError(null);
        setWorkerId((prev) => {
          if (pinnedWorker && workersInclude(c.workers, pinnedWorker)) return pinnedWorker;
          if (prev && workersInclude(c.workers, prev)) return prev;
          if (initialWorker && workersInclude(c.workers, initialWorker)) return initialWorker;
          const stored = readStoredWorker(chatId);
          if (stored && workersInclude(c.workers, stored)) return stored;
          if (workersInclude(c.workers, 'default')) return 'default';
          const ids = workerOptionIds(c.workers);
          return ids[0] ?? '';
        });
        const vault = c.vault;
        const override = (vault?.override_path || '').trim();
        const effective = (vault?.effective_path || '').trim();
        const storedVault = readStoredVaultPath(chatId);
        const actorVault = readActorDefaultVaultPath();
        if (override) {
          setVaultPathState(override);
        } else if (storedVault) {
          setVaultPathState(storedVault);
        } else if (actorVault) {
          setVaultPathState(actorVault);
        } else if (effective) {
          setVaultPathState(effective);
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, [chatId, enabled, initialWorker, pinnedWorker, setWorkerId]);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  useEffect(() => {
    if (!chatId) {
      setWorkerId('');
      return;
    }
    setWorkerId(pinnedWorker || initialWorker || readStoredWorker(chatId) || '');
  }, [chatId, initialWorker, pinnedWorker, setWorkerId]);

  const historyTenantId = (config?.effective_tenant_id || 'default').trim() || 'default';

  const clearLoopHistoryReload = useCallback(() => {
    loopHistoryReloadRef.current.forEach((id) => window.clearTimeout(id));
    loopHistoryReloadRef.current = [];
  }, []);

  const reloadHistory = useCallback((opts?: { force?: boolean }) => {
    if (!enabled || !chatId || config === null) return;
    const force = Boolean(opts?.force);
    if (!force && loadingRef.current) return;
    setHistoryLoading(true);
    adminService
      .getConversation(chatId, historyTenantId)
      .then((data) => {
        if (!force && loadingRef.current) return;
        const fromServer = historyToChatMessages(data.messages, historyTenantId);
        const hasLoopResult = conversationHasLoopResult(fromServer);
        if (hasLoopResult) {
          clearLoopHistoryReload();
        }
        const activeWorker = workerId || initialWorker || '';
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
          return mergeHistoryWithEphemeral(withImages, ephemeral);
        });
      })
      .catch(() => undefined)
      .finally(() => setHistoryLoading(false));
  }, [chatId, clearLoopHistoryReload, config, enabled, historyTenantId, initialWorker, workerId]);

  const loopPollingActive = useMemo(
    () => loopSchedulePolling || conversationIndicatesLoopScheduling(messages),
    [loopSchedulePolling, messages]
  );

  useVisibilityAwareInterval(() => {
    if (!enabled || !chatId || loadingRef.current || config === null) return;
    reloadHistory({ force: true });
  }, loopPollingActive && enabled ? 12_000 : null);

  useEffect(() => {
    return () => {
      loopHistoryReloadRef.current.forEach((id) => window.clearTimeout(id));
      loopHistoryReloadRef.current = [];
    };
  }, []);

  const scheduleLoopHistoryReload = useCallback(() => {
    clearLoopHistoryReload();
    reloadHistory({ force: true });
    const delays = [2_000, 4_000, 6_000, 10_000, 15_000, 20_000, 30_000, 45_000, 60_000, 90_000, 120_000];
    loopHistoryReloadRef.current = delays.map((ms) =>
      window.setTimeout(() => {
        reloadHistory({ force: true });
      }, ms)
    );
  }, [chatId, clearLoopHistoryReload, reloadHistory]);

  useEffect(() => {
    if (!enabled || !chatId || config === null) {
      if (!enabled || !chatId) setHistoryLoading(false);
      return;
    }
    if (loadingRef.current) return;

    setHistoryLoading(true);
    let cancelled = false;
    // Worker al disparar el efecto. NO incluir workerId en deps: setWorkerId tras el
    // GET re-disparaba getConversation en bucle (FloatingAdminChat + playground).
    const workerAtLoad = workerId || initialWorker || '';
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
          const merged = mergeHistoryWithEphemeral(withImages, ephemeral);
          return merged;
        });
        const convWorker = (
          data.preferred_worker_id ||
          data.last_worker_id ||
          ''
        ).trim();
        if (pinnedWorker && workersInclude(config?.workers, pinnedWorker)) {
          setWorkerId(pinnedWorker);
        } else if (convWorker && workersInclude(config?.workers, convWorker)) {
          setWorkerId(convWorker);
        }
        const convVault = (data.vault_db_path || '').trim();
        if (convVault) {
          setVaultPathState(convVault);
          writeStoredVaultPath(chatId, convVault);
        }
      })
      .catch(() => {
        if (!cancelled && !loadingRef.current) {
          const stored = readEphemeralHeartbeats(chatId, workerAtLoad);
          setMessages((prev) => {
            const live = filterEphemeralForWorker(
              collectEphemeralMessages(prev),
              workerAtLoad
            );
            const merged = mergeEphemeralHeartbeats(stored, live);
            return merged.length ? merged : [];
          });
        }
      })
      .finally(() => {
        if (!cancelled) setHistoryLoading(false);
      });
    return () => {
      cancelled = true;
      setHistoryLoading(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- workerId fuera a propósito
  }, [chatId, enabled, historyTenantId, initialWorker, pinnedWorker, setWorkerId, config]);

  useEffect(() => {
    if (!chatId) return;
    writeEphemeralHeartbeats(chatId, workerId, messages);
  }, [chatId, workerId, messages]);

  const scrollContentKey = useMemo(() => {
    const tail = messages
      .slice(-4)
      .map((m) => `${m.role}:${m.text?.length ?? 0}:${m.streaming ? 1 : 0}`)
      .join('|');
    return `${messages.length}|${tail}|${thinking ? 1 : 0}`;
  }, [messages, thinking]);

  const { scrollRef, showScrollButton, scrollToBottom, onScroll } = useChatScrollAnchor(
    scrollContentKey,
    { resetKey: chatId, loading, thinking }
  );

  const runChatTurn = useCallback(
    async (
      text: string,
      payloadImages: { mime_type: string; data_base64: string }[] = [],
      userPreviewImages: ChatImagePreview[] = []
    ) => {
      await runAdminChatTurn({
        text,
        payloadImages,
        userPreviewImages,
        chatId,
        workerId,
        projectId,
        knowledgeScope,
        vaultPath,
        voiceResponseMode,
        effectiveTenantId: config?.effective_tenant_id,
        telegramUserId: config?.telegram_user_id,
        abortControllerRef,
        thinkingStartedAt,
        setLoading,
        setThinking,
        setThinkingIdentity,
        setError,
        setMessages,
        setSessionTokenTotal,
        setContextTokensEstimated,
        setLoopSchedulePolling,
        finalizeCancelledGeneration,
        clearLoopHistoryReload,
        scheduleLoopHistoryReload,
        onConversationActivity,
        onSandboxArtifacts,
      });
    },
    [
      chatId,
      config?.effective_tenant_id,
      config?.telegram_user_id,
      finalizeCancelledGeneration,
      clearLoopHistoryReload,
      onConversationActivity,
      onSandboxArtifacts,
      workerId,
      projectId,
      knowledgeScope,
      vaultPath,
      voiceResponseMode,
      scheduleLoopHistoryReload,
    ]
  );


  const send = useCallback(async () => {
    const text = input.trim();
    const names = imageAttachments.pendingImages.map((p) => p.name);
    const payloadImages = imageAttachments.buildPayloadImages();
    if ((!text && payloadImages.length === 0) || loading || !workerId) return;
    const userPreviewImages = userPreviewsFromPayload(payloadImages, names);
    setInput('');
    imageAttachments.clearImages({ revoke: true });
    await runChatTurn(text, payloadImages, userPreviewImages);
  }, [input, loading, workerId, imageAttachments, runChatTurn]);

  const retryFromMessage = useCallback(
    async (messageIndex: number) => {
      if (loading || !workerId) return;
      const target = messages[messageIndex];
      if (!target || target.role !== 'user') return;
      const text = (target.text || '').trim();
      const payloadImages = payloadImagesFromPreviews(target.imagePreviews);
      if (!text && payloadImages.length === 0) return;
      const userPreviewImages =
        target.imagePreviews?.filter((img) => (img.url || '').trim().startsWith('data:')) ?? [];
      abortControllerRef.current?.abort();
      setMessages((prev) => {
        const removed = prev.slice(messageIndex);
        revokeMessageImagePreviews(removed);
        return prev.slice(0, messageIndex);
      });
      setError(null);
      await runChatTurn(text, payloadImages, userPreviewImages);
    },
    [loading, workerId, messages, runChatTurn]
  );

  /** Carga el mensaje de usuario en el input y recorta el hilo desde ahí (reenvío manual). */
  const editFromMessage = useCallback(
    (messageIndex: number) => {
      if (loading || !workerId) return;
      const target = messages[messageIndex];
      if (!target || target.role !== 'user') return;
      const text = (target.text || '').trim();
      if (!text) return;
      abortControllerRef.current?.abort();
      setLoading(false);
      setThinking(false);
      finalizeCancelledGeneration();
      setMessages((prev) => {
        const removed = prev.slice(messageIndex);
        revokeMessageImagePreviews(removed);
        return prev.slice(0, messageIndex);
      });
      setInput(text);
      setError(null);
      window.requestAnimationFrame(() => {
        const el = inputRef.current;
        if (!el) return;
        el.focus();
        const len = text.length;
        el.setSelectionRange(len, len);
      });
    },
    [loading, workerId, messages, finalizeCancelledGeneration]
  );

  const clearMessages = useCallback(() => {
    clearEphemeralHeartbeats(chatId, workerId);
    clearLegacyEphemeralHeartbeats(chatId);
    setMessages((prev) => {
      revokeMessageImagePreviews(prev);
      return [];
    });
  }, [chatId, workerId]);

  const sendVoiceNote = useCallback(
    async (audioBase64: string) => {
      if (!audioBase64.trim() || loading || !workerId) return;
      primeAudioPlayback();
      abortControllerRef.current?.abort();
      setLoading(true);
      setThinking(false);
      setError(null);
      try {
        const res = await fetch('/api/admin/playground/voice', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', ...mutationHeaders('POST') },
          body: JSON.stringify({
            worker_id: workerId,
            chat_id: chatId,
            project_id: projectId || undefined,
            knowledge_scope: knowledgeScope || undefined,
            audio_base64: audioBase64,
            voice_response: voiceResponseMode,
            language_hint: 'es',
          }),
        });
        const data = (await res.json()) as {
          ok?: boolean;
          transcription?: string;
          response?: string;
          audio_base64?: string | null;
          audio_format?: 'ogg' | 'wav';
          audio_unavailable?: boolean;
          detail?: string;
        };
        if (!res.ok) {
          throw new Error(
            friendlyGatewayError(parseApiErrorDetail(data, res.status))
          );
        }
        const transcription = (data.transcription || '').trim() || '(sin transcripción)';
        const reply = (data.response || '').trim();
        setMessages((m) => [
          ...m,
          { role: 'user', text: transcription, voiceNote: true },
          {
            role: 'assistant',
            text: reply,
            audioBase64: data.audio_base64 || undefined,
            audioFormat: data.audio_format,
            audioUnavailable: Boolean(data.audio_unavailable),
          },
        ]);
        if (data.audio_base64) {
          const playResult = await playTtsAudio(data.audio_base64, {
            format: data.audio_format,
            source: 'voice-note',
          });
          if (!playResult.ok) {
            setMessages((m) => {
              const next = [...m];
              const last = next[next.length - 1];
              if (last?.role === 'assistant') {
                next[next.length - 1] = { ...last, audioPlayError: playResult.reason };
              }
              return next;
            });
          }
        }
        onConversationActivity?.();
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Error enviando nota de voz');
      } finally {
        setLoading(false);
      }
    },
    [loading, workerId, chatId, projectId, knowledgeScope, onConversationActivity, voiceResponseMode]
  );

  return {
    config,
    workerId,
    setWorkerId,
    messages,
    historyLoading,
    input,
    setInput,
    loading,
    thinking,
    thinkingIdentity,
    thinkingStartedAt,
    error,
    scrollRef,
    showScrollButton,
    scrollToBottom,
    onScroll,
    send,
    sendVoiceNote,
    voiceResponseMode,
    voiceResponseAvailable,
    liveVoiceAvailable,
    setVoiceResponseMode,
    retryFromMessage,
    editFromMessage,
    inputRef,
    cancelGeneration,
    clearMessages,
    imageAttachments,
    vaultPath,
    setVaultPath,
    sessionTokenTotal,
    contextTokensEstimated,
    reloadConfig: loadConfig,
    reloadHistory,
  };
}
