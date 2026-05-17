'use client';

import Link from 'next/link';
import { Bot, ChevronRight, Send, X } from 'lucide-react';
import { useAuthStore } from '@/store/authStore';
import { ChatBubble, ThinkingBubble } from '@/components/chat/ChatBubble';
import { useAdminChat, type AdminChatController } from '@/components/chat/useAdminChat';

export type AdminChatPanelProps = {
  chatId: string;
  initialWorker?: string;
  /** Estado compartido (p. ej. widget flotante con botón fuera del panel) */
  chat?: AdminChatController;
  /** Vista compacta para el widget flotante */
  variant?: 'full' | 'compact';
  emptyHint?: string;
  showHeader?: boolean;
  showWorkerLink?: boolean;
  className?: string;
};

export function AdminChatPanel({
  chatId,
  initialWorker,
  chat: chatProp,
  variant = 'full',
  emptyHint,
  showHeader = true,
  showWorkerLink = true,
  className = '',
}: AdminChatPanelProps) {
  const { usuario } = useAuthStore();
  const internalChat = useAdminChat({ chatId, initialWorker, enabled: !chatProp });
  const chat = chatProp ?? internalChat;
  const {
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
  } = chat;

  const isCompact = variant === 'compact';
  const canSend = usuario?.rol === 'admin';

  return (
    <section
      className={`flex flex-col min-w-0 bg-white dark:bg-dark-surface border dark:border-dark-border overflow-hidden ${
        isCompact ? 'rounded-2xl shadow-xl h-full' : 'flex-1 rounded-3xl shadow-sm'
      } ${className}`}
    >
      {showHeader && (
        <header className="flex flex-wrap items-center justify-between gap-2 p-3 border-b dark:border-dark-border shrink-0">
          <div className="flex items-center gap-2 min-w-0">
            <Bot size={isCompact ? 18 : 22} className="shrink-0 text-gov-blue-700 dark:text-dark-cyan" />
            <div className="min-w-0">
              <p className={`font-black dark:text-dark-text truncate ${isCompact ? 'text-sm' : 'text-xl'}`}>
                Asistente
              </p>
              {!isCompact && (
                <p className="text-xs text-gov-gray-500">Respuestas en vivo (SSE)</p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={workerId}
              onChange={(e) => {
                setWorkerId(e.target.value);
                clearMessages();
              }}
              disabled={!config?.workers?.length || config?.authorized === false}
              className="text-xs px-2 py-1.5 border rounded-lg dark:border-dark-border dark:bg-dark-bg max-w-[140px] disabled:opacity-50"
              aria-label="Agente"
            >
              {(config?.workers ?? []).map((w) => (
                <option key={w} value={w}>
                  {w}
                </option>
              ))}
            </select>
            {showWorkerLink && workerId && (
              <Link
                href={`/templates/${workerId}`}
                className="text-[10px] text-gov-blue-700 font-semibold flex items-center gap-0.5 shrink-0"
              >
                Editar <ChevronRight size={10} />
              </Link>
            )}
          </div>
        </header>
      )}

      {config?.team_hint && (
        <p
          className={`text-[10px] px-3 py-1.5 border-b shrink-0 ${
            config.authorized === false
              ? 'bg-red-50 text-red-700 border-red-100 dark:bg-red-950/30 dark:text-red-300 dark:border-red-900'
              : 'bg-gov-gray-50 text-gov-gray-600 border-gov-gray-100 dark:bg-dark-bg dark:text-dark-muted dark:border-dark-border'
          }`}
        >
          {config.team_hint}
          {config.telegram_user_id ? (
            <span className="block font-mono mt-0.5 opacity-80">TG: {config.telegram_user_id}</span>
          ) : null}
        </p>
      )}

      <div
        ref={scrollRef}
        className={`flex-1 overflow-y-auto p-3 space-y-3 min-h-0 ${
          isCompact ? 'max-h-[min(50vh,420px)]' : 'min-h-[320px]'
        }`}
      >
        {messages.length === 0 && (
          <p className="text-sm text-gov-gray-400 text-center py-8">
            {emptyHint ??
              (workerId
                ? `Escribe un mensaje para hablar con ${workerId}`
                : 'Escribe un mensaje para hablar con …')}
          </p>
        )}
        {messages.map((m, i) => {
          const isEmptyStreaming =
            m.role === 'assistant' && m.streaming && !m.text && thinking && i === messages.length - 1;
          if (isEmptyStreaming) {
            return <ThinkingBubble key={`${i}-thinking`} startedAt={thinkingStartedAt.current} />;
          }
          return <ChatBubble key={`${i}-${m.role}`} message={m} />;
        })}
      </div>

      <footer className="p-3 border-t dark:border-dark-border bg-gov-gray-50/50 dark:bg-dark-bg/50 shrink-0">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                void send();
              }
            }}
            rows={isCompact ? 1 : 2}
            placeholder="Mensaje…"
            className="flex-1 px-3 py-2 text-sm border rounded-xl dark:border-dark-border dark:bg-dark-surface resize-none"
            disabled={loading || !canSend}
          />
          {loading ? (
            <button
              type="button"
              onClick={cancelGeneration}
              className="px-3 py-2 border-2 border-red-200 dark:border-red-900/60 text-red-700 dark:text-red-400 bg-white dark:bg-dark-surface rounded-xl font-bold text-xs flex items-center gap-1 shrink-0"
              aria-label="Cancelar"
            >
              <X size={16} aria-hidden /> Cancelar
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void send()}
              disabled={!input.trim() || !canSend}
              className="px-3 py-2 bg-gov-blue-700 text-white rounded-xl font-bold text-xs flex items-center gap-1 disabled:opacity-50 shrink-0"
            >
              <Send size={16} aria-hidden /> Enviar
            </button>
          )}
        </div>
        {error && <p className="text-xs text-red-600 mt-1.5">{error}</p>}
      </footer>
    </section>
  );
}
