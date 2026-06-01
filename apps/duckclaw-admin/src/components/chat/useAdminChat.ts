'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { adminService } from '@/services/adminService';
import type { ChatImagePreview, ChatMsg } from '@/components/chat/types';
import {
  historyToChatMessages,
  preserveImagePreviewsFromPrevious,
  userPreviewsFromPayload,
} from '@/lib/chatMessageImages';
import { useChatImageAttachments } from '@/components/chat/useChatImageAttachments';
import { useChatScrollAnchor } from '@/components/chat/useChatScrollAnchor';
import { requestNotificationPermission } from '@/lib/chatNotifications';
import { artifactPreviewApiPath } from '@/lib/artifactPreview';
import {
  clearEphemeralHeartbeats,
  clearLegacyEphemeralHeartbeats,
  filterEphemeralForWorker,
  mergeEphemeralHeartbeats,
  readEphemeralHeartbeats,
  writeEphemeralHeartbeats,
} from '@/lib/chatEphemeralStorage';
import { workerMatches } from '@/lib/workerOptions';
import { readStoredVaultPath, writeStoredVaultPath } from '@/lib/conversationVaultStorage';
import { workerOptionIds, workersInclude } from '@/lib/workerOptions';
import {
  finalizeRunningToolHeartbeats,
  createToolInvocationId,
  findRunningToolHeartbeatIndex,
  mapSseToolPhase,
  parseToolNameFromHeartbeatText,
  toolHeartbeatDisplayText,
} from '@/lib/toolHeartbeat';

export type UseAdminChatOptions = {
  chatId: string;
  initialWorker?: string;
  projectId?: string;
  enabled?: boolean;
  /** Tras cada turno completado (para refrescar inbox). */
  onConversationActivity?: () => void;
};

function artifactImagePreview(
  tenantId: string,
  artifactId: string
): ChatImagePreview[] {
  const tid = (tenantId || 'default').trim() || 'default';
  const aid = artifactId.trim();
  return [
    {
      url: artifactPreviewApiPath(tid, aid),
      name: `${aid}.png`,
      artifactId: aid,
      tenantId: tid,
    },
  ];
}

/** Heartbeats/plan/tool no están en Redis; conservarlos si recargamos historial en vivo. */
function mergeHistoryWithEphemeral(server: ChatMsg[], ephemeral: ChatMsg[]): ChatMsg[] {
  if (!ephemeral.length) return server;
  return [...server, ...ephemeral];
}

function collectEphemeralMessages(messages: ChatMsg[]): ChatMsg[] {
  return messages.filter((m) => m.role === 'heartbeat');
}

/** True si hay heartbeat de herramienta en el turno actual (entre último user y assistant streaming). */
export function hasToolHeartbeatInCurrentTurn(messages: ChatMsg[]): boolean {
  const streamIdx = messages.findIndex(
    (x, i) => x.role === 'assistant' && x.streaming && i === messages.length - 1
  );
  const end = streamIdx >= 0 ? streamIdx : messages.length;
  for (let i = end - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role === 'user') break;
    if (m.role === 'heartbeat' && m.heartbeatKind === 'tool') return true;
  }
  return false;
}

/** No renderizar burbuja assistant vacía mientras hay tool heartbeats (ThinkingBubble solo sin tools). */
export function shouldSkipEmptyStreamingAssistant(
  message: ChatMsg,
  messages: ChatMsg[]
): boolean {
  if (message.role !== 'assistant' || !message.streaming) return false;
  if ((message.text || '').trim()) return false;
  if (message.imagePreviews?.length) return false;
  return hasToolHeartbeatInCurrentTurn(messages);
}

export function isThinkingStatusHeartbeat(m: ChatMsg | undefined): boolean {
  return (
    m?.role === 'heartbeat' &&
    m.heartbeatKind === 'status' &&
    /^Pensando/i.test((m.text || '').trim())
  );
}

/** Remove stale "Pensando…" status heartbeats from persisted chat history. */
export function stripThinkingStatusHeartbeats(messages: ChatMsg[]): ChatMsg[] {
  return messages.filter((m) => !isThinkingStatusHeartbeat(m));
}

function workerStorageKey(chatId: string): string {
  return `duckclaw-admin-worker-${chatId}`;
}

function revokeMessageImagePreviews(messages: ChatMsg[]): void {
  for (const m of messages) {
    if (!m.imagePreviews?.length) continue;
    for (const img of m.imagePreviews) {
      if (!img.url.startsWith('blob:')) continue;
      try {
        URL.revokeObjectURL(img.url);
      } catch {
        /* ignore */
      }
    }
  }
}

function readStoredWorker(chatId: string): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return sessionStorage.getItem(workerStorageKey(chatId));
  } catch {
    return null;
  }
}

export type AdminChatController = ReturnType<typeof useAdminChat>;

export function useAdminChat({
  chatId,
  initialWorker = '',
  projectId = '',
  enabled = true,
  onConversationActivity,
}: UseAdminChatOptions) {
  const [config, setConfig] = useState<Awaited<ReturnType<typeof adminService.getPlaygroundConfig>> | null>(
    null
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
  const thinkingStartedAt = useRef<number>(0);
  const inputRef = useRef<HTMLTextAreaElement | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const loadingRef = useRef(false);
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
      if (m.length === 0) return m;
      const last = m[m.length - 1];
      if (last?.role !== 'assistant' || !last.streaming) return stripThinkingStatusHeartbeats(m);
      const base = m.slice(0, -1);
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
    setLoading(false);
    setThinking(false);
    finalizeCancelledGeneration();
  }, [finalizeCancelledGeneration]);

  const loadConfig = useCallback(() => {
    if (!enabled) return;
    adminService
      .getPlaygroundConfig(chatId ? { chat_id: chatId } : undefined)
      .then((c) => {
        setConfig(c);
        if (c.authorized === false) {
          setError(c.team_hint || 'Usuario Telegram no autorizado en este tenant');
          setWorkerId('');
          return;
        }
        setError(null);
        setWorkerId((prev) => {
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
        if (override) {
          setVaultPathState(override);
        } else if (storedVault) {
          setVaultPathState(storedVault);
        } else if (effective) {
          setVaultPathState(effective);
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, [chatId, enabled, initialWorker, setWorkerId]);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  useEffect(() => {
    if (!chatId) {
      setWorkerId('');
      return;
    }
    setWorkerId(initialWorker || readStoredWorker(chatId) || '');
  }, [chatId, initialWorker, setWorkerId]);

  const historyTenantId = (config?.effective_tenant_id || 'default').trim() || 'default';

  useEffect(() => {
    if (!enabled || !chatId) {
      setHistoryLoading(false);
      return;
    }
    if (loadingRef.current) return;

    setHistoryLoading(true);
    let cancelled = false;
    adminService
      .getConversation(chatId, historyTenantId)
      .then((data) => {
        if (cancelled || loadingRef.current) return;
        const fromServer = historyToChatMessages(data.messages, historyTenantId);
        const activeWorker = workerId || initialWorker || '';
        const storedEphemeral = readEphemeralHeartbeats(chatId, activeWorker);
        setMessages((prev) => {
          const liveEphemeral = filterEphemeralForWorker(
            collectEphemeralMessages(prev),
            activeWorker
          );
          const ephemeral = mergeEphemeralHeartbeats(storedEphemeral, liveEphemeral);
          const withImages = preserveImagePreviewsFromPrevious(fromServer, prev);
          const merged = mergeHistoryWithEphemeral(withImages, ephemeral);
          return merged;
        });
        const convWorker = (
          data.preferred_worker_id ||
          data.last_worker_id ||
          ''
        ).trim();
        if (convWorker && workersInclude(config?.workers, convWorker)) {
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
          const activeWorker = workerId || initialWorker || '';
          const stored = readEphemeralHeartbeats(chatId, activeWorker);
          setMessages((prev) => {
            const live = filterEphemeralForWorker(
              collectEphemeralMessages(prev),
              activeWorker
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
  }, [chatId, enabled, historyTenantId, workerId, initialWorker, setWorkerId]);

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
    if (!text && payloadImages.length === 0) return;
    void requestNotificationPermission();
    abortControllerRef.current?.abort();
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const userPreviews =
      userPreviewImages.length > 0
        ? userPreviewImages
        : payloadImages.length > 0
          ? userPreviewsFromPayload(payloadImages)
          : undefined;
    const userLabel = text;

    setLoading(true);
    thinkingStartedAt.current = Date.now();
    setThinkingIdentity({ workerId, swarmSlot: 1 });
    setThinking(true);
    setError(null);
    setMessages((m) => [
      ...m,
      {
        role: 'user',
        text: userLabel,
        imagePreviews: userPreviews?.length ? userPreviews : undefined,
      },
      { role: 'assistant', text: '', streaming: true },
    ]);

    const appendAssistant = (chunk: string) => {
      if (chunk) setThinking(false);
      setMessages((m) => {
        if (m.length === 0) return m;
        const next = [...m];
        const last = next[next.length - 1];
        if (last?.role !== 'assistant') return m;
        next[next.length - 1] = { ...last, text: last.text + chunk, streaming: true };
        return next;
      });
    };

    const attachArtifactToStreamingAssistant = (
      artifactId: string,
      tenantId: string
    ) => {
      const previews = artifactImagePreview(tenantId, artifactId);
      setThinking(false);
      setMessages((m) => {
        const idx = m.findIndex(
          (x, i) => x.role === 'assistant' && x.streaming && i === m.length - 1
        );
        if (idx < 0) return m;
        const next = [...m];
        next[idx] = { ...next[idx], imagePreviews: previews };
        return next;
      });
    };

    const appendHeartbeat = (payload: {
      text: string;
      kind?: 'plan' | 'tool' | 'status' | 'visual';
      worker_id?: string;
      swarm_slot?: number;
      artifact_id?: string;
      artifact_tenant_id?: string;
      tool_name?: string;
      tool_phase?: 'start' | 'done' | 'error';
      elapsed_ms?: number;
    }) => {
      const kind = payload.kind ?? 'status';
      const hbWorker = (payload.worker_id || workerId || '').trim();
      const hbSlot =
        payload.swarm_slot != null && Number.isFinite(payload.swarm_slot)
          ? Math.max(1, Math.floor(payload.swarm_slot))
          : 1;
      if (hbWorker || hbSlot > 1) {
        setThinkingIdentity((prev) => ({
          workerId: hbWorker || prev.workerId || workerId,
          swarmSlot: hbSlot,
        }));
      }
      const aid = (payload.artifact_id || '').trim();
      if (aid) {
        const tid =
          (payload.artifact_tenant_id || config?.effective_tenant_id || 'default').trim() ||
          'default';
        void attachArtifactToStreamingAssistant(aid, tid);
      }
      const toolName =
        (payload.tool_name || '').trim() ||
        parseToolNameFromHeartbeatText(payload.text) ||
        undefined;
      let effectiveKind = kind;
      if (effectiveKind === 'tool' && !toolName) {
        // Heartbeat legacy (p. ej. noVNC) sin tool_name: no crear bloque "Usando: tool".
        effectiveKind = 'status';
      }
      const uiPhase = mapSseToolPhase(payload.tool_phase);
      const isToolHb = effectiveKind === 'tool' && Boolean(toolName);
      if (kind === 'tool') {
        setThinking(false);
      }
      setMessages((m) => {
        const streamingIdx = m.findIndex(
          (x, i) => x.role === 'assistant' && x.streaming && i === m.length - 1
        );
        const insertAt = streamingIdx >= 0 ? streamingIdx : m.length;
        const elapsedMs =
          payload.tool_phase === 'done' || payload.tool_phase === 'error'
            ? payload.elapsed_ms
            : undefined;

        if (isToolHb && toolName) {
          const isStart = payload.tool_phase === 'start' || uiPhase === 'running';
          const runningIdx = findRunningToolHeartbeatIndex(m, toolName, insertAt);
          const running = runningIdx >= 0 ? m[runningIdx] : null;

          if (isStart) {
            if (running) {
              const merged: ChatMsg = {
                ...running,
                text: toolHeartbeatDisplayText(toolName, 'running', undefined),
                toolPhase: 'running',
                workerId: hbWorker || running.workerId,
                swarmSlot: hbSlot,
              };
              const next = [...m];
              next[runningIdx] = merged;
              return next;
            }
            const startedAt = Date.now();
            const merged: ChatMsg = {
              role: 'heartbeat',
              text: toolHeartbeatDisplayText(toolName, 'running', undefined),
              heartbeatKind: 'tool',
              workerId: hbWorker || undefined,
              swarmSlot: hbSlot,
              toolName,
              toolInvocationId: createToolInvocationId(toolName),
              toolPhase: 'running',
              toolStartedAt: startedAt,
            };
            const next = [...m];
            next.splice(insertAt, 0, merged);
            return next;
          }

          const targetIdx = runningIdx;
          const existing = targetIdx >= 0 ? m[targetIdx] : null;
          const startedAt = existing?.toolStartedAt ?? Date.now();
          const merged: ChatMsg = {
            role: 'heartbeat',
            text: toolHeartbeatDisplayText(toolName, uiPhase, elapsedMs),
            heartbeatKind: 'tool',
            workerId: hbWorker || existing?.workerId,
            swarmSlot: hbSlot,
            toolName,
            toolInvocationId: existing?.toolInvocationId ?? createToolInvocationId(toolName),
            toolPhase: uiPhase ?? 'done',
            toolStartedAt: startedAt,
            toolElapsedMs:
              elapsedMs != null && Number.isFinite(elapsedMs) ? elapsedMs : undefined,
          };
          if (targetIdx >= 0) {
            const next = [...m];
            next[targetIdx] = merged;
            return next;
          }
          const next = [...m];
          next.splice(insertAt, 0, merged);
          return next;
        }

        const hb: ChatMsg = {
          role: 'heartbeat',
          text: payload.text,
          heartbeatKind: effectiveKind,
          workerId: hbWorker || undefined,
          swarmSlot: hbSlot,
        };
        if (streamingIdx >= 0) {
          const next = [...m];
          next.splice(streamingIdx, 0, hb);
          return next;
        }
        return [...m, hb];
      });
    };

    try {
      let assignedSuffix = '';
      let elapsedFooter = '';
      const streamVisual: {
        figure_base64?: string;
        fly_charts_b64?: string[];
        fly_chart_artifact_ids?: string[];
        artifact_id?: string;
        artifact_tenant_id?: string;
      } = {};
      await adminService.playgroundChatStream(
        {
          worker_id: workerId,
          project_id: projectId || undefined,
          message: text,
          chat_id: chatId,
          tenant_id: config?.effective_tenant_id ?? 'default',
          telegram_user_id: config?.telegram_user_id,
          vault_db_path: vaultPath || undefined,
          images: payloadImages.length ? payloadImages : undefined,
        },
        {
          onToken: appendAssistant,
          onHeartbeat: appendHeartbeat,
          onDone: (meta) => {
            if (meta.assigned_worker_id && meta.assigned_worker_id !== workerId) {
              assignedSuffix = ` (worker: ${meta.assigned_worker_id})`;
            }
            if (meta.elapsed_ms != null && Number.isFinite(meta.elapsed_ms)) {
              elapsedFooter = `\n\nTiempo: ${(meta.elapsed_ms / 1000).toFixed(2)}s`;
            }
            if (
              meta.figure_base64 ||
              meta.fly_charts_b64?.length ||
              meta.fly_chart_artifact_ids?.length ||
              meta.artifact_id
            ) {
              streamVisual.figure_base64 = meta.figure_base64;
              streamVisual.fly_charts_b64 = meta.fly_charts_b64;
              streamVisual.fly_chart_artifact_ids = meta.fly_chart_artifact_ids;
              streamVisual.artifact_id = meta.artifact_id;
              streamVisual.artifact_tenant_id = meta.artifact_tenant_id;
            }
          },
        },
        { signal: abortController.signal }
      );
      if (abortController.signal.aborted) {
        finalizeCancelledGeneration();
        return;
      }
      const tenantForArtifact =
        (streamVisual.artifact_tenant_id || config?.effective_tenant_id || 'default').trim() ||
        'default';
      let assistantPreviews: ChatMsg['imagePreviews'] | undefined;
      const chartNames = ['trading-pnl.png', 'participation-pie.png'];
      const artifactIdsFromFly = (streamVisual.fly_chart_artifact_ids ?? []).filter((id) =>
        id?.trim()
      );
      const chartsFromFly = (streamVisual.fly_charts_b64 ?? []).filter((b) => b?.trim());
      if (artifactIdsFromFly.length > 0) {
        assistantPreviews = artifactIdsFromFly.flatMap((aid, i) =>
          artifactImagePreview(tenantForArtifact, aid).map((p) => ({
            ...p,
            name: chartNames[i] ?? p.name,
          }))
        );
      } else if (chartsFromFly.length > 0) {
        assistantPreviews = chartsFromFly.map((b64, i) => {
          const raw = b64.trim();
          const src = raw.startsWith('data:') ? raw : `data:image/png;base64,${raw}`;
          return { url: src, name: chartNames[i] ?? `chart-${i + 1}.png` };
        });
      } else if (streamVisual.figure_base64?.trim()) {
        const raw = streamVisual.figure_base64.trim();
        const src = raw.startsWith('data:') ? raw : `data:image/png;base64,${raw}`;
        assistantPreviews = [{ url: src, name: 'imagen-generada.png' }];
      } else if (streamVisual.artifact_id) {
        assistantPreviews = artifactImagePreview(tenantForArtifact, streamVisual.artifact_id);
      }
      setMessages((m) => {
        if (m.length === 0) return m;
        const next = [...m];
        const last = next[next.length - 1];
        if (last?.role === 'assistant') {
          const base = last.text || '(sin respuesta)';
          next[next.length - 1] = {
            role: 'assistant',
            text: base + assignedSuffix + elapsedFooter,
            streaming: false,
            imagePreviews: assistantPreviews ?? last.imagePreviews,
          };
        }
        return finalizeRunningToolHeartbeats(stripThinkingStatusHeartbeats(next));
      });
    } catch (e) {
      if (abortController.signal.aborted) {
        finalizeCancelledGeneration();
        return;
      }
      const msg = e instanceof Error ? e.message : 'Error';
      setMessages((m) => {
        const trimmed =
          m.length > 0 && m[m.length - 1]?.role === 'assistant' && m[m.length - 1]?.streaming
            ? m.slice(0, -1)
            : m;
        return stripThinkingStatusHeartbeats([...trimmed, { role: 'error', text: msg }]);
      });
      setError(msg);
    } finally {
      if (abortControllerRef.current === abortController) {
        abortControllerRef.current = null;
      }
      setLoading(false);
      setThinking(false);
      onConversationActivity?.();
    }
  },
    [
      chatId,
      config?.effective_tenant_id,
      config?.telegram_user_id,
      finalizeCancelledGeneration,
      onConversationActivity,
      workerId,
      projectId,
      vaultPath,
      imageAttachments,
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
      if (!text) return;
      abortControllerRef.current?.abort();
      setMessages((prev) => {
        const removed = prev.slice(messageIndex);
        revokeMessageImagePreviews(removed);
        return prev.slice(0, messageIndex);
      });
      setError(null);
      await runChatTurn(text, []);
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
    retryFromMessage,
    editFromMessage,
    inputRef,
    cancelGeneration,
    clearMessages,
    imageAttachments,
    vaultPath,
    setVaultPath,
    reloadConfig: loadConfig,
  };
}
