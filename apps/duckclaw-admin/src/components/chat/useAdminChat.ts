'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { adminService } from '@/services/adminService';
import type { ChatMsg } from '@/components/chat/types';
import { useChatImageAttachments } from '@/components/chat/useChatImageAttachments';
import { useChatScrollAnchor } from '@/components/chat/useChatScrollAnchor';

export type UseAdminChatOptions = {
  chatId: string;
  initialWorker?: string;
  enabled?: boolean;
  /** Tras cada turno completado (para refrescar inbox). */
  onConversationActivity?: () => void;
};

function historyToChatMessages(
  raw: { role: string; content: string }[] | undefined
): ChatMsg[] {
  if (!raw?.length) return [];
  const out: ChatMsg[] = [];
  for (const m of raw) {
    const role = m.role === 'user' ? 'user' : m.role === 'assistant' ? 'assistant' : null;
    const text = (m.content || '').trim();
    if (!role || !text) continue;
    out.push({ role, text });
  }
  return out;
}

function workerStorageKey(chatId: string): string {
  return `duckclaw-admin-worker-${chatId}`;
}

function revokeMessageImagePreviews(messages: ChatMsg[]): void {
  for (const m of messages) {
    if (!m.imagePreviews?.length) continue;
    for (const img of m.imagePreviews) {
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
    (next: string | ((prev: string) => string)) => {
      setWorkerIdState((prev) => {
        const value = typeof next === 'function' ? next(prev) : next;
        if (typeof window !== 'undefined') {
          try {
            sessionStorage.setItem(workerStorageKey(chatId), value);
          } catch {
            /* ignore quota */
          }
        }
        return value;
      });
    },
    [chatId]
  );
  const [messages, setMessages] = useState<ChatMsg[]>([]);
  const [input, setInput] = useState('');
  const imageAttachments = useChatImageAttachments();
  const [loading, setLoading] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [thinkingIdentity, setThinkingIdentity] = useState<{ workerId: string; swarmSlot: number }>({
    workerId: '',
    swarmSlot: 1,
  });
  const [error, setError] = useState<string | null>(null);
  const thinkingStartedAt = useRef<number>(0);
  const abortControllerRef = useRef<AbortController | null>(null);
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

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
      if (last?.role !== 'assistant' || !last.streaming) return m;
      const base = m.slice(0, -1);
      if (last.text.trim()) {
        return [...base, { ...last, streaming: false }];
      }
      return [...base, { role: 'assistant', text: 'Interrumpido', interrupted: true }];
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
          if (prev && c.workers?.includes(prev)) return prev;
          if (initialWorker && c.workers?.includes(initialWorker)) return initialWorker;
          const stored = readStoredWorker(chatId);
          if (stored && c.workers?.includes(stored)) return stored;
          if (c.workers?.includes('default')) return 'default';
          return c.workers?.[0] ?? '';
        });
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Error'));
  }, [chatId, enabled, initialWorker, setWorkerId]);

  useEffect(() => {
    loadConfig();
  }, [loadConfig]);

  useEffect(() => {
    if (!enabled || !chatId) return;
    setMessages((prev) => {
      revokeMessageImagePreviews(prev);
      return [];
    });
    let cancelled = false;
    const tid = config?.effective_tenant_id;
    adminService
      .getConversation(chatId, tid)
      .then((data) => {
        if (cancelled) return;
        setMessages(historyToChatMessages(data.messages));
        if (data.last_worker_id) {
          setWorkerId((prev) => {
            if (prev && config?.workers?.includes(prev)) return prev;
            if (config?.workers?.includes(data.last_worker_id)) return data.last_worker_id;
            return prev;
          });
        }
      })
      .catch(() => {
        if (!cancelled) setMessages([]);
      });
    return () => {
      cancelled = true;
    };
  }, [chatId, enabled, config?.effective_tenant_id, config?.workers, setWorkerId]);

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

  const send = useCallback(async () => {
    const text = input.trim();
    const payloadImages = imageAttachments.buildPayloadImages();
    if ((!text && payloadImages.length === 0) || loading || !workerId) return;
    abortControllerRef.current?.abort();
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    const userPreviews = imageAttachments.buildUserPreviews();
    const userLabel = text;

    setInput('');
    imageAttachments.clearImages({ revoke: false });
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
        imagePreviews: userPreviews.length ? userPreviews : undefined,
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

    const appendHeartbeat = (payload: {
      text: string;
      kind?: 'plan' | 'tool' | 'status';
      worker_id?: string;
      swarm_slot?: number;
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
      setMessages((m) => {
        const streamingIdx = m.findIndex(
          (x, i) => x.role === 'assistant' && x.streaming && !x.text && i === m.length - 1
        );
        const hb: ChatMsg = {
          role: 'heartbeat',
          text: payload.text,
          heartbeatKind: kind,
          workerId: hbWorker || undefined,
          swarmSlot: hbSlot,
        };
        if (streamingIdx >= 0) {
          const insertAt = streamingIdx;
          const prev = insertAt > 0 ? m[insertAt - 1] : null;
          if (
            prev?.role === 'heartbeat' &&
            prev.heartbeatKind === 'tool' &&
            kind === 'tool'
          ) {
            const next = [...m];
            next[insertAt - 1] = hb;
            return next;
          }
          const next = [...m];
          next.splice(insertAt, 0, hb);
          return next;
        }
        const last = m[m.length - 1];
        if (last?.role === 'heartbeat' && last.heartbeatKind === 'tool' && kind === 'tool') {
          const next = [...m];
          next[next.length - 1] = hb;
          return next;
        }
        return [...m, hb];
      });
    };

    try {
      let assignedSuffix = '';
      let elapsedFooter = '';
      await adminService.playgroundChatStream(
        {
          worker_id: workerId,
          message: text,
          chat_id: chatId,
          tenant_id: config?.effective_tenant_id ?? 'default',
          telegram_user_id: config?.telegram_user_id,
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
              elapsedFooter = `\n\n⏱️ ${(meta.elapsed_ms / 1000).toFixed(2)}s`;
            }
          },
        },
        { signal: abortController.signal }
      );
      if (abortController.signal.aborted) {
        finalizeCancelledGeneration();
        return;
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
          };
        }
        return next;
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
        return [...trimmed, { role: 'error', text: msg }];
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
  }, [
    chatId,
    config?.effective_tenant_id,
    finalizeCancelledGeneration,
    input,
    loading,
    config?.telegram_user_id,
    onConversationActivity,
    workerId,
    imageAttachments,
  ]);

  const clearMessages = useCallback(() => {
    setMessages((prev) => {
      revokeMessageImagePreviews(prev);
      return [];
    });
  }, []);

  return {
    config,
    workerId,
    setWorkerId,
    messages,
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
    cancelGeneration,
    clearMessages,
    imageAttachments,
  };
}
