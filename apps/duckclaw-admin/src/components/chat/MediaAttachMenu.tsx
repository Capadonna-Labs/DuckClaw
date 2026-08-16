'use client';

import { useEffect, useRef, useState } from 'react';
import {
  FileText,
  ImagePlus,
  Mic,
  Paperclip,
  ClipboardPaste,
  PhoneCall,
  Square,
  Volume2,
  VolumeX,
} from 'lucide-react';

export type MediaAttachMenuProps = {
  canSend: boolean;
  loading: boolean;
  voiceRecording: boolean;
  voiceBusy: boolean;
  voiceResponseMode: boolean;
  voiceResponseAvailable: boolean;
  liveVoiceAvailable?: boolean;
  liveVoiceActive?: boolean;
  imageCount: number;
  documentCount?: number;
  maxImages?: number;
  maxDocuments?: number;
  /** Botones sin borde para barra de composición tipo AI Studio. */
  variant?: 'default' | 'minimal';
  onPickImage: () => void;
  onPickFile?: () => void;
  onPaste?: () => void;
  onToggleVoiceResponse: () => void;
  onVoiceNoteClick: () => void;
  onLiveVoiceClick?: () => void;
};

export function MediaAttachMenu({
  canSend,
  loading,
  voiceRecording,
  voiceBusy,
  voiceResponseMode,
  voiceResponseAvailable,
  liveVoiceAvailable = false,
  liveVoiceActive = false,
  imageCount,
  documentCount = 0,
  maxImages = 15,
  maxDocuments = 5,
  variant = 'default',
  onPickImage,
  onPickFile,
  onPaste,
  onToggleVoiceResponse,
  onVoiceNoteClick,
  onLiveVoiceClick,
}: MediaAttachMenuProps) {
  const isMinimal = variant === 'minimal';
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const closeOnOutside = (event: MouseEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', closeOnOutside);
    return () => document.removeEventListener('mousedown', closeOnOutside);
  }, [open]);

  const imageDisabled =
    !canSend || loading || voiceRecording || imageCount >= maxImages;
  const fileDisabled =
    !onPickFile || !canSend || loading || voiceRecording || documentCount >= maxDocuments;
  const ttsDisabled = !canSend || !voiceResponseAvailable;
  const ttsUnavailableTitle = voiceResponseAvailable
    ? undefined
    : 'Sensory TTS no disponible (configura DUCKCLAW_SENSORY_BASE_URL y arranca sensory_node)';
  const micDisabled = !canSend || (loading && !voiceRecording) || voiceBusy || liveVoiceActive;
  const liveVoiceDisabled = !canSend || loading || voiceRecording || voiceBusy;
  const liveVoiceUnavailableTitle = liveVoiceAvailable
    ? undefined
    : 'Pipecat no disponible (DUCKCLAW_VOICE_ENABLED + DuckClaw-Voice PM2)';

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={!canSend && !voiceRecording}
        className={`shrink-0 disabled:opacity-50 ${
          isMinimal
            ? `p-2 rounded-full text-gov-gray-500 hover:bg-gov-gray-100 dark:hover:bg-dark-bg dark:text-dark-muted ${
                voiceRecording ? 'text-red-600 dark:text-red-400' : open ? 'text-gov-blue-700 dark:text-dark-cyan' : ''
              }`
            : `px-2 py-2 border rounded-xl ${
                voiceRecording
                  ? 'border-red-300 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400'
                  : open
                    ? 'border-gov-blue-300 bg-gov-blue-50 text-gov-blue-800 dark:border-gov-blue-800 dark:bg-gov-blue-950/40 dark:text-gov-blue-200'
                    : 'dark:border-dark-border'
              }`
        }`}
        aria-label="Adjuntar multimedia"
        aria-haspopup="menu"
        aria-expanded={open}
        title="Adjuntar multimedia"
      >
        <Paperclip size={18} aria-hidden />
      </button>
      {open && (
        <div
          role="menu"
          className="absolute bottom-full right-0 mb-2 w-[13.5rem] max-w-[calc(100vw-1.5rem)] rounded-xl border bg-white dark:bg-dark-surface dark:border-dark-border shadow-lg p-1 z-[60] origin-bottom-right"
        >
          <button
            type="button"
            role="menuitem"
            disabled={imageDisabled}
            onClick={() => {
              onPickImage();
              setOpen(false);
            }}
            className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-left hover:bg-gov-gray-100 dark:hover:bg-dark-bg disabled:opacity-50"
          >
            <ImagePlus size={16} className="shrink-0" aria-hidden />
            <span className="truncate">Imagen</span>
          </button>
          {onPickFile ? (
            <button
              type="button"
              role="menuitem"
              disabled={fileDisabled}
              onClick={() => {
                onPickFile();
                setOpen(false);
              }}
              className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-left hover:bg-gov-gray-100 dark:hover:bg-dark-bg disabled:opacity-50"
            >
              <FileText size={16} className="shrink-0" aria-hidden />
              <span className="truncate">Archivo</span>
            </button>
          ) : null}
          {onPaste ? (
            <button
              type="button"
              role="menuitem"
              disabled={!canSend || loading || voiceRecording}
              onClick={() => {
                void onPaste();
                setOpen(false);
              }}
              className="w-full flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-left hover:bg-gov-gray-100 dark:hover:bg-dark-bg disabled:opacity-50"
            >
              <ClipboardPaste size={16} className="shrink-0" aria-hidden />
              <span className="truncate">Pegar</span>
            </button>
          ) : null}
          <button
            type="button"
            role="menuitem"
            disabled={ttsDisabled}
            onClick={onToggleVoiceResponse}
            title={ttsUnavailableTitle}
            className={`w-full flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-left hover:bg-gov-gray-100 dark:hover:bg-dark-bg disabled:opacity-50 ${
              voiceResponseMode
                ? 'text-gov-blue-800 dark:text-gov-blue-200 font-semibold'
                : 'text-gov-gray-600 dark:text-dark-muted'
            }`}
            aria-pressed={voiceResponseMode}
            aria-disabled={ttsDisabled}
          >
            {voiceResponseMode ? (
              <Volume2 size={16} className="shrink-0" aria-hidden />
            ) : (
              <VolumeX size={16} className="shrink-0" aria-hidden />
            )}
            <span className="truncate">Voz automática</span>
          </button>
          <button
            type="button"
            role="menuitem"
            disabled={liveVoiceDisabled || !liveVoiceAvailable}
            title={liveVoiceUnavailableTitle}
            onClick={() => {
              onLiveVoiceClick?.();
              setOpen(false);
            }}
            className={`w-full flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-left hover:bg-gov-gray-100 dark:hover:bg-dark-bg disabled:opacity-50 ${
              liveVoiceActive ? 'text-red-700 dark:text-red-400 font-semibold' : ''
            }`}
          >
            <PhoneCall size={16} className="shrink-0" aria-hidden />
            <span className="truncate">{liveVoiceActive ? 'Colgar voz en vivo' : 'Voz en vivo'}</span>
          </button>
          <button
            type="button"
            role="menuitem"
            disabled={micDisabled}
            onClick={() => {
              void onVoiceNoteClick();
              if (!voiceRecording) setOpen(false);
            }}
            className={`w-full flex items-center gap-2 rounded-lg px-3 py-2 text-sm text-left hover:bg-gov-gray-100 dark:hover:bg-dark-bg disabled:opacity-50 ${
              voiceRecording ? 'text-red-700 dark:text-red-400 font-semibold' : ''
            }`}
          >
            {voiceRecording ? (
              <Square size={16} className="shrink-0" aria-hidden />
            ) : (
              <Mic size={16} className="shrink-0" aria-hidden />
            )}
            <span className="truncate">{voiceRecording ? 'Enviar nota de voz' : 'Nota de voz'}</span>
          </button>
        </div>
      )}
    </div>
  );
}
