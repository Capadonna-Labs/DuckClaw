'use client';

import type { ClipboardEvent, Dispatch, ReactNode, RefObject, SetStateAction } from 'react';
import { FileText, Send, X } from 'lucide-react';
import { LiveVoiceBar } from '@/components/chat/LiveVoiceBar';
import { MediaAttachMenu } from '@/components/chat/MediaAttachMenu';
import type { useChatImageAttachments } from '@/components/chat/useChatImageAttachments';
import type { useChatDocumentAttachments } from '@/components/chat/useChatDocumentAttachments';
import { CHAT_DOCUMENT_ACCEPT } from '@/lib/chatDocumentAttachments';
import type {
  LiveVoiceSpeakingPhase,
  LiveVoiceStatus,
} from '@/components/chat/usePipecatLiveVoice';

type ImageAttachments = ReturnType<typeof useChatImageAttachments>;
type DocumentAttachments = ReturnType<typeof useChatDocumentAttachments>;

export type AdminChatComposeFooterProps = {
  isStudioCompose: boolean;
  isCompact: boolean;
  composeChips?: ReactNode;
  input: string;
  setInput: (value: string) => void;
  inputRef: RefObject<HTMLTextAreaElement>;
  canSend: boolean;
  canSubmit: boolean;
  loading: boolean;
  workerId: string;
  workerDisplayName: string;
  error: string | null;
  voiceResponseMode: boolean;
  voiceResponseAvailable: boolean;
  liveVoiceAvailable: boolean;
  setVoiceResponseMode: Dispatch<SetStateAction<boolean>>;
  imageAttachments: ImageAttachments;
  documentAttachments: DocumentAttachments;
  send: () => void | Promise<void>;
  cancelGeneration: () => void;
  onTextareaPaste: (e: ClipboardEvent<HTMLTextAreaElement>) => void;
  pasteFromClipboard: () => void | Promise<void>;
  handleVoiceClick: () => void | Promise<void>;
  handleLiveVoiceClick: () => void | Promise<void>;
  voice: {
    recording: boolean;
    busy: boolean;
    error: string | null;
  };
  liveVoice: {
    status: LiveVoiceStatus;
    speakingPhase: LiveVoiceSpeakingPhase;
    elapsedLabel: string;
    userSubtitle: string;
    botSubtitle: string;
    error: string | null;
    isActive: boolean;
    endCall: () => void | Promise<void>;
  };
};

function PendingDocumentChips({
  documentAttachments,
}: {
  documentAttachments: DocumentAttachments;
}) {
  if (documentAttachments.pendingDocuments.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-2">
      {documentAttachments.pendingDocuments.map((doc) => (
        <div
          key={doc.id}
          className="relative inline-flex max-w-[14rem] items-center gap-1.5 rounded-lg border border-gov-gray-200 bg-white px-2 py-1.5 text-xs dark:border-dark-border dark:bg-dark-surface"
        >
          <FileText size={14} className="shrink-0 text-gov-blue-700 dark:text-dark-cyan" aria-hidden />
          <span className="truncate font-medium" title={doc.name}>
            {doc.name}
          </span>
          <button
            type="button"
            onClick={() => documentAttachments.removeDocument(doc.id)}
            className="shrink-0 rounded-full p-0.5 text-gov-gray-500 hover:bg-gov-gray-100 dark:hover:bg-dark-bg"
            aria-label={`Quitar ${doc.name}`}
          >
            <X size={12} />
          </button>
        </div>
      ))}
    </div>
  );
}

export function AdminChatComposeFooter({
  isStudioCompose,
  isCompact,
  composeChips,
  input,
  setInput,
  inputRef,
  canSend,
  canSubmit,
  loading,
  workerId,
  workerDisplayName,
  error,
  voiceResponseMode,
  voiceResponseAvailable,
  liveVoiceAvailable,
  setVoiceResponseMode,
  imageAttachments,
  documentAttachments,
  send,
  cancelGeneration,
  onTextareaPaste,
  pasteFromClipboard,
  handleVoiceClick,
  handleLiveVoiceClick,
  voice,
  liveVoice,
}: AdminChatComposeFooterProps) {
  const attachError = imageAttachments.attachError || documentAttachments.attachError;

  return (
      <footer
        className={`p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] shrink-0 relative z-20 ${
          isStudioCompose
            ? 'bg-white dark:bg-dark-surface border-t dark:border-dark-border'
            : 'border-t dark:border-dark-border bg-gov-gray-50/50 dark:bg-dark-bg/50'
        }`}
      >
        <LiveVoiceBar
          status={liveVoice.status}
          speakingPhase={liveVoice.speakingPhase}
          workerLabel={workerDisplayName}
          elapsedLabel={liveVoice.elapsedLabel}
          userSubtitle={liveVoice.userSubtitle}
          botSubtitle={liveVoice.botSubtitle}
          error={liveVoice.error}
          onHangUp={() => void liveVoice.endCall()}
        />
        <input
          ref={imageAttachments.fileInputRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          multiple
          className="hidden"
          onChange={(e) => void imageAttachments.onPickFiles(e.target.files)}
        />
        <input
          ref={documentAttachments.fileInputRef}
          type="file"
          accept={CHAT_DOCUMENT_ACCEPT}
          multiple
          className="hidden"
          onChange={(e) => void documentAttachments.onPickFiles(e.target.files)}
        />

        {isStudioCompose ? (
          <div className="rounded-2xl border border-gov-gray-200 bg-gov-gray-50/80 dark:border-dark-border dark:bg-dark-bg/60 shadow-sm focus-within:border-gov-blue-300 focus-within:ring-2 focus-within:ring-gov-blue-100 dark:focus-within:ring-gov-blue-900/40 transition-shadow">
            {(imageAttachments.pendingImages.length > 0 ||
              documentAttachments.pendingDocuments.length > 0) && (
              <div className="flex flex-col gap-2 px-3 pt-3">
                {imageAttachments.pendingImages.length > 0 && (
                  <div className="flex flex-wrap gap-2">
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
                <PendingDocumentChips documentAttachments={documentAttachments} />
              </div>
            )}
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onPaste={onTextareaPaste}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  void send();
                }
              }}
              rows={2}
              placeholder="Escribe un mensaje…"
              className="w-full min-h-[3rem] max-h-40 resize-none bg-transparent px-4 pt-3 pb-1 text-sm text-gov-gray-900 placeholder:text-gov-gray-400 focus:outline-none dark:text-dark-text dark:placeholder:text-dark-muted"
              disabled={!canSend || liveVoice.isActive}
            />
            <div className="flex items-end justify-between gap-2 px-2 pb-2 pt-0.5">
              <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1">{composeChips}</div>
              <div className="flex shrink-0 items-center gap-0.5">
                <MediaAttachMenu
                  variant="minimal"
                  canSend={canSend && Boolean(workerId)}
                  loading={loading}
                  voiceRecording={voice.recording}
                  voiceBusy={voice.busy}
                  voiceResponseMode={voiceResponseMode}
                  voiceResponseAvailable={voiceResponseAvailable}
                  liveVoiceAvailable={liveVoiceAvailable}
                  liveVoiceActive={liveVoice.isActive}
                  imageCount={imageAttachments.pendingImages.length}
                  documentCount={documentAttachments.pendingDocuments.length}
                  onPickImage={() => imageAttachments.fileInputRef.current?.click()}
                  onPickFile={() => documentAttachments.fileInputRef.current?.click()}
                  onPaste={() => void pasteFromClipboard()}
                  onToggleVoiceResponse={() => setVoiceResponseMode((v) => !v)}
                  onVoiceNoteClick={() => void handleVoiceClick()}
                  onLiveVoiceClick={() => void handleLiveVoiceClick()}
                />
                {loading ? (
                  <button
                    type="button"
                    onClick={cancelGeneration}
                    className="flex h-9 w-9 items-center justify-center rounded-full border-2 border-red-200 text-red-700 dark:border-red-900/60 dark:text-red-400"
                    aria-label="Cancelar"
                    title="Cancelar"
                  >
                    <X size={16} aria-hidden />
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => void send()}
                    disabled={!canSubmit}
                    className="flex h-9 min-w-[2.25rem] items-center justify-center gap-1 rounded-full bg-gov-blue-700 px-3 text-white disabled:opacity-40 hover:bg-gov-blue-800 dark:bg-gov-blue-600"
                    aria-label="Enviar"
                    title="Enviar"
                  >
                    <Send size={16} aria-hidden />
                  </button>
                )}
              </div>
            </div>
          </div>
        ) : (
          <>
            {composeChips ? (
              <div className="mb-2 flex flex-wrap items-center gap-1.5">{composeChips}</div>
            ) : null}
            {(imageAttachments.pendingImages.length > 0 ||
              documentAttachments.pendingDocuments.length > 0) && (
              <div className="mb-2 flex flex-col gap-2">
                {imageAttachments.pendingImages.length > 0 && (
                  <div className="flex flex-wrap gap-2">
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
                <PendingDocumentChips documentAttachments={documentAttachments} />
              </div>
            )}
            <div className="flex gap-2">
              <MediaAttachMenu
                canSend={canSend && Boolean(workerId)}
                loading={loading}
                voiceRecording={voice.recording}
                voiceBusy={voice.busy}
                voiceResponseMode={voiceResponseMode}
                voiceResponseAvailable={voiceResponseAvailable}
                liveVoiceAvailable={liveVoiceAvailable}
                liveVoiceActive={liveVoice.isActive}
                imageCount={imageAttachments.pendingImages.length}
                documentCount={documentAttachments.pendingDocuments.length}
                onPickImage={() => imageAttachments.fileInputRef.current?.click()}
                onPickFile={() => documentAttachments.fileInputRef.current?.click()}
                onPaste={() => void pasteFromClipboard()}
                onToggleVoiceResponse={() => setVoiceResponseMode((v) => !v)}
                onVoiceNoteClick={() => void handleVoiceClick()}
                onLiveVoiceClick={() => void handleLiveVoiceClick()}
              />
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onPaste={onTextareaPaste}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    void send();
                  }
                }}
                rows={isCompact ? 1 : 2}
                placeholder="Mensaje…"
                className="flex-1 px-3 py-2 text-sm border rounded-xl dark:border-dark-border dark:bg-dark-surface resize-none"
                disabled={!canSend || liveVoice.isActive}
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
          </>
        )}
        {voice.recording ? (
          <p className="text-xs text-red-600 mt-1.5">Grabando… pulsa el cuadrado para enviar la nota de voz.</p>
        ) : loading && voice.busy ? (
          <p className="text-xs text-gov-gray-500 mt-1.5">Transcribiendo nota de voz y generando respuesta…</p>
        ) : null}
        {(attachError || error || voice.error || liveVoice.error) && (
          <p className="text-xs text-red-600 mt-1.5">
            {attachError || error || voice.error || liveVoice.error}
          </p>
        )}
      </footer>
  );
}
