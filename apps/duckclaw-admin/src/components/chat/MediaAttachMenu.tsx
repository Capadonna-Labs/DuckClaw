'use client';

import { useEffect, useRef, useState } from 'react';
import { ImagePlus, Mic, Paperclip, Square, Volume2, VolumeX } from 'lucide-react';

export type MediaAttachMenuProps = {
  canSend: boolean;
  loading: boolean;
  voiceRecording: boolean;
  voiceBusy: boolean;
  voiceResponseMode: boolean;
  voiceResponseAvailable: boolean;
  imageCount: number;
  maxImages?: number;
  onPickImage: () => void;
  onToggleVoiceResponse: () => void;
  onVoiceNoteClick: () => void;
};

export function MediaAttachMenu({
  canSend,
  loading,
  voiceRecording,
  voiceBusy,
  voiceResponseMode,
  voiceResponseAvailable,
  imageCount,
  maxImages = 3,
  onPickImage,
  onToggleVoiceResponse,
  onVoiceNoteClick,
}: MediaAttachMenuProps) {
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
  const ttsDisabled = !canSend || !voiceResponseAvailable;
  const ttsUnavailableTitle = voiceResponseAvailable
    ? undefined
    : 'Sensory TTS no disponible (configura DUCKCLAW_SENSORY_BASE_URL y arranca sensory_node)';
  const micDisabled = !canSend || (loading && !voiceRecording) || voiceBusy;

  return (
    <div ref={rootRef} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        disabled={!canSend && !voiceRecording}
        className={`px-2 py-2 border rounded-xl shrink-0 disabled:opacity-50 ${
          voiceRecording
            ? 'border-red-300 bg-red-50 text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400'
            : open
              ? 'border-gov-blue-300 bg-gov-blue-50 text-gov-blue-800 dark:border-gov-blue-800 dark:bg-gov-blue-950/40 dark:text-gov-blue-200'
              : 'dark:border-dark-border'
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
          className="absolute bottom-full left-0 mb-2 min-w-[11.5rem] rounded-xl border bg-white dark:bg-dark-surface dark:border-dark-border shadow-lg p-1 z-50"
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
            <ImagePlus size={16} aria-hidden />
            Imagen
          </button>
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
            {voiceResponseMode ? <Volume2 size={16} aria-hidden /> : <VolumeX size={16} aria-hidden />}
            Voz automática
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
            {voiceRecording ? <Square size={16} aria-hidden /> : <Mic size={16} aria-hidden />}
            {voiceRecording ? 'Enviar nota de voz' : 'Nota de voz'}
          </button>
        </div>
      )}
    </div>
  );
}
