'use client';

import { PhoneOff, Radio } from 'lucide-react';
import type { LiveVoiceSpeakingPhase, LiveVoiceStatus } from '@/components/chat/usePipecatLiveVoice';

export type LiveVoiceBarProps = {
  status: LiveVoiceStatus;
  speakingPhase: LiveVoiceSpeakingPhase;
  workerLabel: string;
  elapsedLabel: string;
  userSubtitle?: string;
  botSubtitle?: string;
  error?: string | null;
  onHangUp: () => void;
};

function phaseLabel(phase: LiveVoiceSpeakingPhase): string {
  switch (phase) {
    case 'user':
      return 'Escuchando';
    case 'bot':
      return 'Hablando';
    case 'graph':
      return 'Pensando';
    default:
      return 'En llamada';
  }
}

export function LiveVoiceBar({
  status,
  speakingPhase,
  workerLabel,
  elapsedLabel,
  userSubtitle,
  botSubtitle,
  error,
  onHangUp,
}: LiveVoiceBarProps) {
  if (status === 'idle' && !error) return null;

  const subtitle = botSubtitle?.trim() || userSubtitle?.trim() || '';
  const active = status === 'connected' || status === 'connecting';

  return (
    <div
      className={`mb-2 rounded-xl border px-3 py-2 text-sm ${
        status === 'error'
          ? 'border-red-200 bg-red-50 text-red-800 dark:border-red-900/60 dark:bg-red-950/30 dark:text-red-300'
          : 'border-gov-blue-100 bg-gov-blue-50/80 text-gov-blue-900 dark:border-gov-blue-900/50 dark:bg-gov-blue-950/30 dark:text-gov-blue-100'
      }`}
      role="status"
      aria-live="polite"
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <span
            className={`inline-flex h-2.5 w-2.5 shrink-0 rounded-full ${
              active ? 'animate-pulse bg-red-500' : 'bg-gov-gray-400'
            }`}
            aria-hidden
          />
          <Radio size={14} className="shrink-0 opacity-70" aria-hidden />
          <span className="truncate font-semibold">
            Voz en vivo · {workerLabel || '…'} · {elapsedLabel}
          </span>
        </div>
        <button
          type="button"
          onClick={() => void onHangUp()}
          disabled={status === 'disconnecting'}
          className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-red-200 px-2 py-1 text-xs font-semibold text-red-700 hover:bg-red-100 disabled:opacity-50 dark:border-red-900/60 dark:text-red-300 dark:hover:bg-red-950/40"
          aria-label="Colgar llamada de voz"
        >
          <PhoneOff size={14} aria-hidden />
          Colgar
        </button>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs opacity-80">
        <span>{phaseLabel(speakingPhase)}</span>
        {status === 'connecting' ? <span>Conectando…</span> : null}
        {status === 'disconnecting' ? <span>Colgando…</span> : null}
        {error ? <span className="text-red-700 dark:text-red-300">{error}</span> : null}
      </div>
      {subtitle ? (
        <p className="mt-1 line-clamp-2 text-xs opacity-90" title={subtitle}>
          {subtitle}
        </p>
      ) : null}
    </div>
  );
}
