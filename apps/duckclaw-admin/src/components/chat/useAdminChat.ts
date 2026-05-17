'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { adminService } from '@/services/adminService';
import type { ChatMsg } from '@/components/chat/types';

export type UseAdminChatOptions = {
  chatId: string;
  initialWorker?: string;
  enabled?: boolean;
};

function workerStorageKey(chatId: string): string {
  return `duckclaw-admin-worker-${chatId}`;
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

export function useAdminChat({ chatId, initialWorker = '', enabled = true }: UseAdminChatOptions) {
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
  const [loading, setLoading] = useState(false);
  const [thinking, setThinking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const thinkingStartedAt = useRef<number>(0);
  const abortControllerRef = useRef<AbortController | null>(null);

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
      .getPlaygroundConfig()
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
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages, loading, thinking]);

  const send = useCallback(async () => {
    const text = input.trim();
    if (!text || loading || !workerId) return;
    abortControllerRef.current?.abort();
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    setInput('');
    setLoading(true);
    thinkingStartedAt.current = Date.now();
    setThinking(true);
    setError(null);
    setMessages((m) => [
      ...m,
      { role: 'user', text },
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

    try {
      let assignedSuffix = '';
      await adminService.playgroundChatStream(
        {
          worker_id: workerId,
          message: text,
          chat_id: chatId,
          tenant_id: config?.effective_tenant_id ?? 'default',
          telegram_user_id: config?.telegram_user_id,
        },
        {
          onToken: appendAssistant,
          onDone: (meta) => {
            if (meta.assigned_worker_id && meta.assigned_worker_id !== workerId) {
              assignedSuffix = ` (worker: ${meta.assigned_worker_id})`;
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
            text: base + assignedSuffix,
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
    }
  }, [
    chatId,
    config?.effective_tenant_id,
    finalizeCancelledGeneration,
    input,
    loading,
    workerId,
  ]);

  const clearMessages = useCallback(() => setMessages([]), []);

  return {
    config,
    workerId,
    setWorkerId,
    messages,
    input,
    setInput,
    loading,
    thinking,
    thinkingStartedAt,
    error,
    scrollRef,
    send,
    cancelGeneration,
    clearMessages,
  };
}
