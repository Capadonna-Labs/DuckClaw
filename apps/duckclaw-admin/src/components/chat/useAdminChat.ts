'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { adminService } from '@/services/adminService';
import type { ChatImagePreview, ChatMsg } from '@/components/chat/types';
import {
  payloadImagesFromPreviews,
  userPreviewsFromPayload,
} from '@/lib/chatMessageImages';
import { useChatImageAttachments } from '@/components/chat/useChatImageAttachments';
import { useChatDocumentAttachments } from '@/components/chat/useChatDocumentAttachments';
import { useChatScrollAnchor } from '@/components/chat/useChatScrollAnchor';
import {
  clearEphemeralHeartbeats,
  clearLegacyEphemeralHeartbeats,
} from '@/lib/chatEphemeralStorage';
import { workerMatches } from '@/lib/workerOptions';
import {
  readActorDefaultVaultPath,
  readStoredVaultPath,
  writeStoredVaultPath,
} from '@/lib/conversationVaultStorage';
import { workerOptionIds, workersInclude } from '@/lib/workerOptions';
import { mutationHeaders } from '@/lib/csrfClient';
import { friendlyGatewayError, parseApiErrorDetail } from '@/lib/adminErrors';
import { playTtsAudio, primeAudioPlayback } from '@/lib/playTtsAudio';
import { finalizeRunningToolHeartbeats } from '@/lib/toolHeartbeat';

import {
  readStoredWorker,
  revokeMessageImagePreviews,
  stripThinkingStatusHeartbeats,
  workerStorageKey,
} from './adminChatPure';
import { runAdminChatTurn } from './runAdminChatTurn';
import { useAdminChatHistory } from './useAdminChatHistory';
import type { UsageTokenBreakdown } from '@/lib/formatTokenCount';


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
  /** GET historial 404: limpiar sessionId activo y re-bootstrap. */
  onConversationNotFound?: () => void;
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
  onConversationNotFound,
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
    if (prev && workerId && !workerMatches(prev, workerId)) {
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
  const documentAttachments = useChatDocumentAttachments();
  const [loading, setLoading] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [thinkingIdentity, setThinkingIdentity] = useState<{ workerId: string; swarmSlot: number }>({
    workerId: '',
    swarmSlot: 1,
  });
  const [error, setError] = useState<string | null>(null);
  const [vaultPath, setVaultPathState] = useState('');
  const [lastTurnUsage, setLastTurnUsage] = useState<UsageTokenBreakdown | null>(null);
  const [contextEstimatedTokens, setContextEstimatedTokens] = useState<number | null>(null);
  const thinkingStartedAt = useRef<number>(0);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const loadingRef = useRef(false);
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
    setLastTurnUsage(null);
    setContextEstimatedTokens(null);
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
          if (pinnedWorker && (workersInclude(c.workers, pinnedWorker) || pinnedWorker === 'default')) {
            return pinnedWorker;
          }
          if (prev && (workersInclude(c.workers, prev) || prev === 'default')) return prev;
          if (initialWorker && (workersInclude(c.workers, initialWorker) || initialWorker === 'default')) {
            return initialWorker;
          }
          const stored = readStoredWorker(chatId);
          if (stored && (workersInclude(c.workers, stored) || stored === 'default')) return stored;
          const selected = String(c.selected_worker_id || '').trim();
          if (selected) return selected;
          if (workersInclude(c.workers, 'default')) return 'default';
          const ids = workerOptionIds(c.workers);
          return ids[0] ?? 'default';
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
    const preferred = pinnedWorker || initialWorker || readStoredWorker(chatId) || '';
    if (preferred) {
      setWorkerId(preferred);
      return;
    }
    // Sin preferencia explícita: no vaciar. loadConfig / historial eligen default|primer worker.
  }, [chatId, initialWorker, pinnedWorker, setWorkerId]);

  const { reloadHistory, scheduleLoopHistoryReload, clearLoopHistoryReload } = useAdminChatHistory({
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
    // Pasar el useCallback estable: un wrapper inline re-dispara el effect de
    // getConversation en bucle (deps [setWorkerId] + setHistoryLoading).
    setWorkerId,
    setVaultPathState,
    setHistoryLoading,
    onConversationNotFound,
  });

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
      userPreviewImages: ChatImagePreview[] = [],
      payloadDocuments: { filename: string; mime_type: string; data_base64: string }[] = [],
      documentNames: string[] = []
    ) => {
      await runAdminChatTurn({
        text,
        payloadImages,
        payloadDocuments,
        userPreviewImages,
        documentNames,
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
        setLastTurnUsage,
        setContextEstimatedTokens,
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
    const docNames = documentAttachments.pendingDocuments.map((p) => p.name);
    const payloadDocuments = documentAttachments.buildPayloadDocuments();
    if (
      (!text && payloadImages.length === 0 && payloadDocuments.length === 0) ||
      loading ||
      !workerId
    ) {
      return;
    }
    const userPreviewImages = userPreviewsFromPayload(payloadImages, names);
    setInput('');
    imageAttachments.clearImages({ revoke: true });
    documentAttachments.clearDocuments();
    await runChatTurn(text, payloadImages, userPreviewImages, payloadDocuments, docNames);
  }, [input, loading, workerId, imageAttachments, documentAttachments, runChatTurn]);

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
    documentAttachments,
    vaultPath,
    setVaultPath,
    lastTurnUsage,
    contextEstimatedTokens,
    reloadConfig: loadConfig,
    reloadHistory,
  };
}
