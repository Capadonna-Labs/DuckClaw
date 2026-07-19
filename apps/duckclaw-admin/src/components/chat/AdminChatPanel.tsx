'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  Bot,
  Brain,
  ChevronRight,
  Cpu,
  MessageSquarePlus,
  Settings2,
} from 'lucide-react';
import { usePipecatLiveVoice } from '@/components/chat/usePipecatLiveVoice';
import { useVoiceNoteRecorder } from '@/components/chat/useVoiceNoteRecorder';
import type { ConversationManagePanelProps } from '@/components/chat/ConversationManagePanel';
import { useAuthStore } from '@/store/authStore';
import { EditableConversationTitle } from '@/components/chat/EditableConversationTitle';
import {
  useAdminChat,
  type AdminChatController,
} from '@/components/chat/useAdminChat';
import { AdminChatMessageList } from '@/components/chat/AdminChatMessageList';
import { AdminChatComposeFooter } from '@/components/chat/AdminChatComposeFooter';
import { ChatLlmSelectors } from '@/components/chat/ChatLlmSelectors';
import { ChatSlmSelector } from '@/components/chat/ChatSlmSelector';
import { ConversationQuickPicker } from '@/components/chat/ConversationQuickPicker';
import { ConversationVaultSelector } from '@/components/chat/ConversationVaultSelector';
import { workerOptionId, workerOptionLabel, resolveWorkerDisplayName } from '@/lib/workerOptions';
import { PlaygroundChatStudioHeader } from '@/components/playground/PlaygroundChatStudioHeader';
import { useComposeClipboard } from '@/components/chat/useComposeClipboard';

export type AdminChatPanelProps = {
  chatId: string;
  initialWorker?: string;
  /** Bloquea el selector de worker (p. ej. página Reportes → ui_designer). */
  lockWorkerId?: string;
  /** Estado compartido (p. ej. widget flotante con botón fuera del panel) */
  chat?: AdminChatController;
  /** Vista compacta para el widget flotante */
  variant?: 'full' | 'compact';
  emptyHint?: string;
  showHeader?: boolean;
  /** Cabecera AI Studio (título + tokens) cuando showHeader es false. */
  showStudioHeader?: boolean;
  showWorkerLink?: boolean;
  /** Sección actual (p. ej. VNC, Tablero) → título «VNC/Asistente». */
  sectionTitle?: string;
  /** Título de la conversación activa (inbox). */
  conversationTitle?: string | null;
  onRenameConversation?: (title: string) => Promise<void>;
  headerActions?: React.ReactNode;
  /** Pills de contexto (BD, sandbox, RAG) encima del textarea — estilo barra de composición. */
  composeChips?: React.ReactNode;
  /** `studio`: caja única redondeada con chips dentro (Playground). */
  composeLayout?: 'default' | 'studio';
  /** Compatibilidad: los contenedores pueden resolver gestión de conversaciones fuera del panel base. */
  conversationManage?: Pick<
    ConversationManagePanelProps,
    'tenantId' | 'section' | 'refreshToken' | 'onSelect' | 'onCreateNew'
  >;
  className?: string;
};

function chatPanelTitle(_sectionTitle?: string): string {
  return 'Asistente';
}

export function AdminChatPanel({
  chatId,
  initialWorker,
  lockWorkerId,
  chat: chatProp,
  variant = 'full',
  emptyHint,
  showHeader = true,
  showStudioHeader = false,
  showWorkerLink = true,
  sectionTitle,
  conversationTitle,
  onRenameConversation,
  headerActions,
  composeChips,
  composeLayout = 'default',
  conversationManage,
  className = '',
}: AdminChatPanelProps) {
  const { usuario } = useAuthStore();
  const [compactConfigOpen, setCompactConfigOpen] = useState(false);
  const internalChat = useAdminChat({
    chatId,
    initialWorker,
    lockWorker: lockWorkerId,
    enabled: !chatProp,
  });
  const chat = chatProp ?? internalChat;
  const workerLocked = Boolean((lockWorkerId || '').trim());
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
    liveVoiceAvailable,
    setVoiceResponseMode,
    retryFromMessage,
    editFromMessage,
    inputRef,
    cancelGeneration,
    imageAttachments,
    vaultPath,
    setVaultPath,
    sessionTokenTotal,
    contextTokensEstimated,
    reloadConfig,
    reloadHistory,
  } = chat;

  const isCompact = variant === 'compact';

  const resolvedWorkerLabel = useMemo(() => {
    return resolveWorkerDisplayName(config?.workers, workerId);
  }, [config?.workers, workerId]);

  const workerDisplayName = resolvedWorkerLabel || 'Agente';

  const labelForWorkerId = useCallback(
    (id?: string) => resolveWorkerDisplayName(config?.workers, id || workerId) || workerDisplayName,
    [config?.workers, workerId, workerDisplayName]
  );

  const liveVoice = usePipecatLiveVoice({
    enabled: liveVoiceAvailable,
    onDisconnected: () => reloadHistory(),
  });

  const voiceAppState = useMemo(
    () => ({
      chat_id: chatId,
      worker_id: workerId,
      tenant_id: (config?.effective_tenant_id || 'default').trim() || 'default',
      vault_path: vaultPath || undefined,
      section: sectionTitle,
      variant: isCompact ? ('bubble' as const) : ('playground' as const),
    }),
    [chatId, workerId, config?.effective_tenant_id, vaultPath, sectionTitle, isCompact]
  );

  useEffect(() => {
    if (liveVoice.isConnected) {
      void liveVoice.endCall();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- colgar al cambiar conversación o worker
  }, [chatId, workerId]);

  useEffect(() => {
    if (!liveVoice.isConnected) return;
    liveVoice.sendAppState(voiceAppState);
  }, [liveVoice, liveVoice.isConnected, voiceAppState]);

  const compactConversationLabel =
    conversationTitle?.trim() ||
    (chatId && chatId.length > 28
      ? `${chatId.slice(0, 12)}…${chatId.slice(-10)}`
      : chatId) ||
    'Sin título';
  const isStudioCompose = composeLayout === 'studio';
  const canSend = usuario?.rol === 'admin';
  const canSubmit =
    canSend &&
    Boolean(workerId) &&
    !loading &&
    !liveVoice.isActive &&
    (input.trim().length > 0 || imageAttachments.hasImages);

  const voice = useVoiceNoteRecorder();

  const handleLiveVoiceClick = useCallback(async () => {
    if (!workerId || !chatId) return;
    await liveVoice.toggleCall(voiceAppState);
  }, [chatId, liveVoice, voiceAppState, workerId]);

  const { onTextareaPaste, pasteFromClipboard } = useComposeClipboard({
    canSend,
    input,
    setInput,
    inputRef,
    ingestFiles: imageAttachments.ingestFiles,
    setAttachError: imageAttachments.setAttachError,
  });

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
            <div className="flex flex-col items-stretch gap-2 w-full min-w-0">
              <div className="flex items-center justify-between gap-2 w-full">
                <div className="min-w-0">
                  <p className="text-sm font-black dark:text-dark-text truncate">
                    {chatPanelTitle(sectionTitle)}
                  </p>
                  <p className="text-[10px] text-gov-gray-500 truncate">
                    {workerDisplayName}
                  </p>
                </div>
                <div className="flex items-center gap-0.5 shrink-0">
                  {conversationManage?.onCreateNew ? (
                    <button
                      type="button"
                      onClick={() => void conversationManage.onCreateNew?.()}
                      className="p-1.5 rounded-lg text-gov-blue-700 hover:bg-gov-gray-100 dark:hover:bg-dark-bg"
                      title="Nueva conversación"
                      aria-label="Nueva conversación"
                    >
                      <MessageSquarePlus size={16} />
                    </button>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => setCompactConfigOpen((v) => !v)}
                    className={`p-1.5 rounded-lg hover:bg-gov-gray-100 dark:hover:bg-dark-bg ${
                      compactConfigOpen
                        ? 'text-gov-blue-700 bg-gov-blue-50 dark:bg-dark-bg'
                        : 'text-gov-gray-500'
                    }`}
                    title="Configuración del chat"
                    aria-label="Configuración del chat"
                    aria-expanded={compactConfigOpen}
                  >
                    <Settings2 size={16} />
                  </button>
                  {headerActions}
                </div>
              </div>
              {conversationManage && (
                <ConversationQuickPicker
                  tenantId={conversationManage.tenantId}
                  section={conversationManage.section}
                  activeSessionId={chatId}
                  refreshToken={conversationManage.refreshToken}
                  onSelect={conversationManage.onSelect}
                  onCreateNew={conversationManage.onCreateNew}
                  conversationTitle={compactConversationLabel}
                  onRenameConversation={onRenameConversation}
                />
              )}
              {compactConfigOpen ? (
                <div className="rounded-xl border border-gov-blue-50 bg-gov-gray-50/80 p-2 space-y-2 dark:border-dark-border dark:bg-dark-bg">
                  {chatId ? (
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
                  ) : null}
                  {chatId && (config?.catalog?.length ?? 0) > 0 ? (
                    <label className="flex flex-col gap-1 text-[10px] w-full min-w-0">
                      <span className="flex items-center gap-2 text-gov-gray-500 dark:text-dark-muted shrink-0">
                        <Brain size={14} className="text-gov-blue-600 dark:text-dark-cyan shrink-0" />
                        LLM
                      </span>
                      <ChatLlmSelectors
                        chatId={chatId}
                        provider={config?.llm?.provider ?? ''}
                        model={config?.llm?.model ?? ''}
                        catalog={config?.catalog ?? []}
                        mlxInference={config?.slm}
                        onUpdated={() => reloadConfig()}
                        disabled={config?.authorized === false || loading}
                        compact
                      />
                    </label>
                  ) : null}
                  {chatId ? (
                    <label className="flex flex-col gap-1 text-[10px] w-full min-w-0">
                      <span className="flex items-center gap-2 text-gov-gray-500 dark:text-dark-muted shrink-0">
                        <Cpu size={14} className="text-gov-blue-600 dark:text-dark-cyan shrink-0" />
                        SLM (opcional)
                      </span>
                      <ChatSlmSelector
                        chatId={chatId}
                        slm={config?.slm}
                        onUpdated={() => reloadConfig()}
                        disabled={config?.authorized === false || loading}
                        compact
                      />
                    </label>
                  ) : null}
                  <label className="flex flex-col gap-1 text-[10px] w-full min-w-0">
                    <span className="flex items-center gap-2 text-gov-gray-500 dark:text-dark-muted shrink-0">
                      <Bot size={14} className="text-gov-blue-600 dark:text-dark-cyan shrink-0" />
                      Worker
                    </span>
                    <select
                      value={workerId}
                      onChange={(e) => setWorkerId(e.target.value, { persist: true })}
                      disabled={
                        workerLocked ||
                        !config?.workers?.length ||
                        config?.authorized === false
                      }
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
              ) : null}
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
                  <div className="flex flex-col gap-2 min-w-0">
                    <span className="text-[10px] font-black uppercase tracking-wider text-gov-gray-500 dark:text-dark-muted">
                      LLM
                    </span>
                    <ChatLlmSelectors
                      chatId={chatId}
                      provider={config?.llm?.provider ?? ''}
                      model={config?.llm?.model ?? ''}
                      catalog={config?.catalog ?? []}
                      mlxInference={config?.slm}
                      onUpdated={() => reloadConfig()}
                      disabled={config?.authorized === false || loading}
                      compact={false}
                    />
                  </div>
                )}
                {chatId && (
                  <div className="flex flex-col gap-2 min-w-0">
                    <span className="text-[10px] font-black uppercase tracking-wider text-gov-gray-500 dark:text-dark-muted">
                      SLM (opcional)
                    </span>
                    <ChatSlmSelector
                      chatId={chatId}
                      slm={config?.slm}
                      onUpdated={() => reloadConfig()}
                      disabled={config?.authorized === false || loading}
                      compact={false}
                    />
                  </div>
                )}
                <select
                  value={workerId}
                  onChange={(e) => setWorkerId(e.target.value, { persist: true })}
                  disabled={
                    workerLocked ||
                    !config?.workers?.length ||
                    config?.authorized === false
                  }
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

      {showStudioHeader && !showHeader ? (
        <PlaygroundChatStudioHeader
          conversationTitle={conversationTitle}
          onRenameConversation={onRenameConversation}
          tokenTotal={sessionTokenTotal}
          contextEstimated={contextTokensEstimated}
        />
      ) : null}

      {config?.team_hint && showHeader && !isCompact && (
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

      <AdminChatMessageList
        messages={messages}
        emptyHint={emptyHint}
        workerId={workerId}
        workerDisplayName={workerDisplayName}
        thinking={thinking}
        thinkingStartedAt={thinkingStartedAt}
        thinkingIdentity={thinkingIdentity}
        labelForWorkerId={labelForWorkerId}
        loading={loading}
        isCompact={isCompact}
        scrollRef={scrollRef}
        showScrollButton={showScrollButton}
        onScroll={onScroll}
        scrollToBottom={scrollToBottom}
        retryFromMessage={retryFromMessage}
        editFromMessage={editFromMessage}
      />

      <AdminChatComposeFooter
        isStudioCompose={isStudioCompose}
        isCompact={isCompact}
        composeChips={composeChips}
        input={input}
        setInput={setInput}
        inputRef={inputRef}
        canSend={canSend}
        canSubmit={canSubmit}
        loading={loading}
        workerId={workerId}
        workerDisplayName={workerDisplayName}
        error={error}
        voiceResponseMode={voiceResponseMode}
        voiceResponseAvailable={voiceResponseAvailable}
        liveVoiceAvailable={liveVoiceAvailable}
        setVoiceResponseMode={setVoiceResponseMode}
        imageAttachments={imageAttachments}
        send={send}
        cancelGeneration={cancelGeneration}
        onTextareaPaste={onTextareaPaste}
        pasteFromClipboard={pasteFromClipboard}
        handleVoiceClick={handleVoiceClick}
        handleLiveVoiceClick={handleLiveVoiceClick}
        voice={voice}
        liveVoice={liveVoice}
      />
    </section>
  );
}
