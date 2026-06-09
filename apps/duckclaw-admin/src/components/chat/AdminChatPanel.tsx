'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import {
  Bot,
  Brain,
  ChevronDown,
  ChevronRight,
  Send,
  X,
} from 'lucide-react';
import { MediaAttachMenu } from '@/components/chat/MediaAttachMenu';
import { useVoiceNoteRecorder } from '@/components/chat/useVoiceNoteRecorder';
import { ChatViewTabBar, type ChatViewTab } from '@/components/chat/ChatViewTabBar';
import {
  ConversationManagePanel,
  type ConversationManagePanelProps,
} from '@/components/chat/ConversationManagePanel';
import { useAuthStore } from '@/store/authStore';
import { ChatBubble, ThinkingBubble } from '@/components/chat/ChatBubble';
import { EditableConversationTitle } from '@/components/chat/EditableConversationTitle';
import {
  hasToolHeartbeatInCurrentTurn,
  isThinkingStatusHeartbeat,
  shouldSkipEmptyStreamingAssistant,
  useAdminChat,
  type AdminChatController,
} from '@/components/chat/useAdminChat';
import { ChatLlmSelectors } from '@/components/chat/ChatLlmSelectors';
import { ConversationVaultSelector } from '@/components/chat/ConversationVaultSelector';
import { workerOptionId, workerOptionLabel } from '@/lib/workerOptions';

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
  /** Sección actual (p. ej. VNC, Tablero) → título «VNC/Asistente». */
  sectionTitle?: string;
  /** Título de la conversación activa (inbox). */
  conversationTitle?: string | null;
  onRenameConversation?: (title: string) => Promise<void>;
  headerActions?: React.ReactNode;
  /** Pestaña «Conversación» (selector, renombrar, nueva/eliminar). */
  conversationManage?: Pick<
    ConversationManagePanelProps,
    'tenantId' | 'section' | 'refreshToken' | 'onSelect' | 'onCreateNew'
  >;
  className?: string;
};

function chatPanelTitle(sectionTitle?: string): string {
  const base = 'Asistente';
  const section = (sectionTitle || '').trim();
  if (!section || section === 'DuckClaw Admin') return base;
  return `${section}/${base}`;
}

export function AdminChatPanel({
  chatId,
  initialWorker,
  chat: chatProp,
  variant = 'full',
  emptyHint,
  showHeader = true,
  showWorkerLink = true,
  sectionTitle,
  conversationTitle,
  onRenameConversation,
  headerActions,
  conversationManage,
  className = '',
}: AdminChatPanelProps) {
  const [viewTab, setViewTab] = useState<ChatViewTab>('chat');
  const showConversationTab = Boolean(conversationManage && chatId && onRenameConversation);

  useEffect(() => {
    setViewTab('chat');
  }, [chatId]);
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
    setVoiceResponseMode,
    retryFromMessage,
    editFromMessage,
    inputRef,
    cancelGeneration,
    imageAttachments,
    vaultPath,
    setVaultPath,
    reloadConfig,
  } = chat;

  const isCompact = variant === 'compact';
  const canSend = usuario?.rol === 'admin';
  const canSubmit =
    canSend &&
    workerId &&
    !loading &&
    (input.trim().length > 0 || imageAttachments.hasImages);

  const voice = useVoiceNoteRecorder();

  const handleVoiceClick = useCallback(async () => {
    if (voice.recording) {
      voice.setBusy(true);
      try {
        const b64 = await voice.stopAndGetBase64();
        if (b64) await sendVoiceNote(b64);
      } finally {
        voice.setBusy(false);
      }
      return;
    }
    await voice.startRecording();
  }, [voice, sendVoiceNote]);

  return (
    <section
      className={`flex flex-col min-w-0 min-h-0 bg-white dark:bg-dark-surface border dark:border-dark-border overflow-hidden ${
        isCompact ? 'rounded-2xl shadow-xl h-full' : 'flex-1 rounded-3xl shadow-sm'
      } ${className}`}
    >
      {showHeader && (
        <header
          className={`border-b dark:border-dark-border shrink-0 ${
            isCompact ? 'p-3 space-y-2' : 'flex flex-wrap items-center justify-between gap-2 p-3'
          }`}
        >
          {isCompact ? (
            <div className="flex flex-col items-stretch gap-2 w-full min-w-0 max-sm:max-h-[10.5rem] max-sm:overflow-y-auto max-sm:overscroll-contain">
              <div className="flex items-center justify-between gap-2 w-full">
                <div className="min-w-0">
                  <p className="text-sm font-black dark:text-dark-text truncate">
                    {chatPanelTitle(sectionTitle)}
                  </p>
                  <p className="text-[10px] text-gov-gray-500 truncate">
                    {conversationTitle?.trim() || 'Respuestas en vivo'}
                  </p>
                </div>
                {headerActions}
              </div>
              {chatId && (
                <ConversationVaultSelector
                  chatId={chatId}
                  tenantId={config?.effective_tenant_id}
                  value={vaultPath}
                  effectivePath={config?.vault?.effective_path}
                  scope={config?.vault?.scope}
                  options={config?.vault_options}
                  onChange={setVaultPath}
                  onUpdated={() => reloadConfig()}
                  disabled={config?.authorized === false}
                  compact
                />
              )}
              {chatId && (config?.catalog?.length ?? 0) > 0 && (
                <label className="flex flex-col gap-1 text-[10px] w-full min-w-0">
                  <span className="flex items-center gap-2 text-gov-gray-500 dark:text-dark-muted shrink-0">
                    <Brain size={14} className="text-gov-blue-600 dark:text-dark-cyan shrink-0" />
                    Modelo
                  </span>
                  <ChatLlmSelectors
                    chatId={chatId}
                    provider={config?.llm?.provider ?? ''}
                    model={config?.llm?.model ?? ''}
                    catalog={config?.catalog ?? []}
                    onUpdated={() => reloadConfig()}
                    disabled={config?.authorized === false || loading}
                    compact
                  />
                </label>
              )}
              <label className="flex flex-col gap-1 text-[10px] w-full min-w-0">
                <span className="flex items-center gap-2 text-gov-gray-500 dark:text-dark-muted shrink-0">
                  <Bot size={14} className="text-gov-blue-600 dark:text-dark-cyan shrink-0" />
                  Worker
                </span>
                <select
                  value={workerId}
                  onChange={(e) => setWorkerId(e.target.value, { persist: true })}
                  disabled={!config?.workers?.length || config?.authorized === false}
                  className="text-[10px] px-1.5 py-2 min-h-[40px] border rounded-md dark:border-dark-border dark:bg-dark-bg w-full max-w-full disabled:opacity-50"
                  aria-label="Worker"
                >
                  {(config?.workers ?? []).map((w) => {
                    const id = workerOptionId(w);
                    const label = workerOptionLabel(w);
                    return (
                      <option key={id} value={id}>
                        {label}
                      </option>
                    );
                  })}
                </select>
              </label>
            </div>
          ) : (
            <>
              <div className="flex items-center gap-2 min-w-0">
                <Bot size={22} className="shrink-0 text-gov-blue-700 dark:text-dark-cyan" />
                <div className="min-w-0">
                  <p className="font-black dark:text-dark-text truncate text-xl">
                    {chatPanelTitle(sectionTitle)}
                  </p>
                  {onRenameConversation && conversationTitle?.trim() ? (
                    <EditableConversationTitle
                      value={conversationTitle.trim()}
                      onSave={onRenameConversation}
                      compact
                      className="text-xs text-gov-gray-500"
                    />
                  ) : (
                    <p className="text-xs text-gov-gray-500 truncate">
                      {conversationTitle?.trim() || 'Respuestas en vivo (SSE)'}
                    </p>
                  )}
                </div>
              </div>
              <div className="flex flex-wrap items-center gap-2 justify-end">
                {chatId && (
                  <ConversationVaultSelector
                    chatId={chatId}
                    tenantId={config?.effective_tenant_id}
                    value={vaultPath}
                    effectivePath={config?.vault?.effective_path}
                    scope={config?.vault?.scope}
                    options={config?.vault_options}
                    onChange={setVaultPath}
                    onUpdated={() => reloadConfig()}
                    disabled={config?.authorized === false}
                    compact={false}
                  />
                )}
                {chatId && (config?.catalog?.length ?? 0) > 0 && (
                  <ChatLlmSelectors
                    chatId={chatId}
                    provider={config?.llm?.provider ?? ''}
                    model={config?.llm?.model ?? ''}
                    catalog={config?.catalog ?? []}
                    onUpdated={() => reloadConfig()}
                    disabled={config?.authorized === false || loading}
                    compact={false}
                  />
                )}
                <select
                  value={workerId}
                  onChange={(e) => setWorkerId(e.target.value, { persist: true })}
                  disabled={!config?.workers?.length || config?.authorized === false}
                  className="text-xs px-2 py-1.5 border rounded-lg dark:border-dark-border dark:bg-dark-bg max-w-[140px] disabled:opacity-50"
                  aria-label="Agente"
                >
                  {(config?.workers ?? []).map((w) => {
                    const id = workerOptionId(w);
                    const label = workerOptionLabel(w);
                    return (
                      <option key={id} value={id}>
                        {label}
                      </option>
                    );
                  })}
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
            </>
          )}
        </header>
      )}

      {config?.team_hint && viewTab === 'chat' && (
        <p
          className={`text-[10px] px-3 py-1.5 border-b shrink-0 ${
            config.authorized === false
              ? 'bg-red-50 text-red-700 border-red-100 dark:bg-red-950/30 dark:text-red-300 dark:border-red-900'
              : 'bg-gov-gray-50 text-gov-gray-600 border-gov-gray-100 dark:bg-dark-bg dark:text-dark-muted dark:border-dark-border'
          }`}
        >
          {config.team_hint}
          {conversationTitle?.trim() ? (
            <span className="block mt-0.5 font-medium truncate" title={conversationTitle.trim()}>
              {conversationTitle.trim()}
            </span>
          ) : null}
        </p>
      )}

      {showConversationTab ? (
        <ChatViewTabBar active={viewTab} onChange={setViewTab} />
      ) : null}

      {showConversationTab && viewTab === 'conversation' && conversationManage ? (
        <ConversationManagePanel
          tenantId={conversationManage.tenantId}
          section={conversationManage.section}
          activeSessionId={chatId}
          conversationTitle={conversationTitle}
          refreshToken={conversationManage.refreshToken}
          onSelect={conversationManage.onSelect}
          onCreateNew={conversationManage.onCreateNew}
          onRename={onRenameConversation}
          onAfterChange={() => setViewTab('chat')}
        />
      ) : (
        <>
      <div className="relative flex-1 min-h-0 min-w-0 flex flex-col w-full">
        <div
          ref={scrollRef}
          onScroll={onScroll}
          className={`flex-1 overflow-y-auto overflow-x-hidden p-3 space-y-3 min-h-0 w-full ${
            isCompact ? '' : 'min-h-[320px]'
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
          const next = messages[i + 1];
          if (
            isThinkingStatusHeartbeat(m) &&
            next?.role === 'assistant' &&
            next.streaming &&
            !next.text &&
            thinking
          ) {
            return null;
          }
          const isEmptyStreaming =
            m.role === 'assistant' && m.streaming && !m.text && thinking && i === messages.length - 1;
          if (isEmptyStreaming && !hasToolHeartbeatInCurrentTurn(messages)) {
            return (
              <ThinkingBubble
                key={`${i}-thinking`}
                startedAt={thinkingStartedAt.current}
                workerId={thinkingIdentity.workerId || workerId}
                swarmSlot={thinkingIdentity.swarmSlot}
              />
            );
          }
          if (shouldSkipEmptyStreamingAssistant(m, messages)) {
            return null;
          }
          const prevUserIdx =
            m.role === 'assistant' && !m.streaming
              ? (() => {
                  for (let j = i - 1; j >= 0; j--) {
                    if (messages[j]?.role === 'user') return j;
                  }
                  return -1;
                })()
              : -1;
          return (
            <ChatBubble
              key={
                m.toolInvocationId
                  ? `${i}-${m.role}-${m.toolInvocationId}`
                  : `${i}-${m.role}`
              }
              message={m}
              canRetry={
                !loading &&
                ((m.role === 'user' &&
                  (Boolean(m.text?.trim()) || Boolean(m.imagePreviews?.length))) ||
                  (m.role === 'assistant' && prevUserIdx >= 0))
              }
              onRetry={
                m.role === 'user'
                  ? () => void retryFromMessage(i)
                  : m.role === 'assistant' && prevUserIdx >= 0
                    ? () => void retryFromMessage(prevUserIdx)
                    : undefined
              }
              canEdit={!loading && m.role === 'user' && Boolean(m.text?.trim())}
              onEdit={m.role === 'user' ? () => editFromMessage(i) : undefined}
            />
          );
        })}
        </div>
        {showScrollButton && (
          <button
            type="button"
            onClick={() => scrollToBottom('smooth')}
            className="absolute bottom-3 right-3 z-10 flex h-9 w-9 items-center justify-center rounded-full bg-gov-blue-700 text-white shadow-lg ring-2 ring-white/80 hover:bg-gov-blue-800 dark:ring-dark-surface max-lg:bottom-16"
            aria-label="Ir al final de la conversación"
            title="Ir abajo"
          >
            <ChevronDown size={20} aria-hidden />
          </button>
        )}
      </div>

      <footer className="p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] border-t dark:border-dark-border bg-gov-gray-50/50 dark:bg-dark-bg/50 shrink-0 relative z-20">
        {imageAttachments.pendingImages.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-2">
            {imageAttachments.pendingImages.map((img) => (
              <div className="relative" key={img.id}>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={img.previewUrl}
                  alt={img.name}
                  className="h-14 w-14 object-cover rounded-lg border dark:border-dark-border"
                />
                <button
                  type="button"
                  onClick={() => imageAttachments.removeImage(img.id)}
                  className="absolute -top-1 -right-1 p-0.5 rounded-full bg-red-600 text-white"
                  aria-label="Quitar imagen"
                >
                  <X size={12} />
                </button>
              </div>
            ))}
          </div>
        )}
        <div className="flex gap-2">
          <input
            ref={imageAttachments.fileInputRef}
            type="file"
            accept="image/jpeg,image/png,image/webp"
            multiple
            className="hidden"
            onChange={(e) => void imageAttachments.onPickFiles(e.target.files)}
          />
          <MediaAttachMenu
            canSend={canSend && Boolean(workerId)}
            loading={loading}
            voiceRecording={voice.recording}
            voiceBusy={voice.busy}
            voiceResponseMode={voiceResponseMode}
            voiceResponseAvailable={voiceResponseAvailable}
            imageCount={imageAttachments.pendingImages.length}
            onPickImage={() => imageAttachments.fileInputRef.current?.click()}
            onToggleVoiceResponse={() => setVoiceResponseMode((v) => !v)}
            onVoiceNoteClick={() => void handleVoiceClick()}
          />
          <textarea
            ref={inputRef}
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
            disabled={!canSend}
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
              disabled={!canSubmit}
              className="px-3 py-2 bg-gov-blue-700 text-white rounded-xl font-bold text-xs flex items-center gap-1 disabled:opacity-50 shrink-0"
            >
              <Send size={16} aria-hidden /> Enviar
            </button>
          )}
        </div>
        {voice.recording ? (
          <p className="text-xs text-red-600 mt-1.5">Grabando… pulsa el cuadrado para enviar la nota de voz.</p>
        ) : loading && voice.busy ? (
          <p className="text-xs text-gov-gray-500 mt-1.5">Transcribiendo nota de voz y generando respuesta…</p>
        ) : null}
        {(imageAttachments.attachError || error || voice.error) && (
          <p className="text-xs text-red-600 mt-1.5">
            {imageAttachments.attachError || error || voice.error}
          </p>
        )}
      </footer>
        </>
      )}
    </section>
  );
}
