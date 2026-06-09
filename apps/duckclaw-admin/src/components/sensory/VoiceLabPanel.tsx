'use client';

import { useCallback, useState } from 'react';
import { Mic, Square, Volume2 } from 'lucide-react';
import { useVoiceNoteRecorder } from '@/components/chat/useVoiceNoteRecorder';
import { mutationHeaders } from '@/lib/csrfClient';
import { friendlyGatewayError, parseApiErrorDetail } from '@/lib/adminErrors';

type VoiceResult = {
  ok?: boolean;
  transcription?: string;
  response?: string;
  audio_base64?: string | null;
  audio_unavailable?: boolean;
  detail?: string;
  stt_processing_ms?: number;
  tts_latency_ms?: number | null;
};

export function VoiceLabPanel() {
  const [result, setResult] = useState<VoiceResult | null>(null);
  const [workerId, setWorkerId] = useState('default');
  const {
    recording,
    busy,
    setBusy,
    error,
    setError,
    startRecording,
    stopAndGetBase64,
  } = useVoiceNoteRecorder();

  const sendVoice = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const audio_base64 = await stopAndGetBase64();
      if (!audio_base64) return;
      const res = await fetch('/api/admin/playground/voice', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...mutationHeaders('POST') },
        body: JSON.stringify({
          worker_id: workerId,
          chat_id: 'admin-voice-lab',
          audio_base64,
          voice_response: true,
          language_hint: 'es',
        }),
      });
      const data = (await res.json()) as VoiceResult & { detail?: string };
      if (!res.ok) {
        throw new Error(friendlyGatewayError(parseApiErrorDetail(data, res.status)));
      }
      setResult(data);
      if (data.audio_base64) {
        const audio = new Audio(`data:audio/ogg;base64,${data.audio_base64}`);
        void audio.play();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Error enviando voz');
    } finally {
      setBusy(false);
    }
  }, [stopAndGetBase64, setBusy, setError, workerId]);

  const replayAudio = useCallback(() => {
    if (!result?.audio_base64) return;
    const audio = new Audio(`data:audio/ogg;base64,${result.audio_base64}`);
    void audio.play();
  }, [result]);

  const onStart = useCallback(() => {
    setResult(null);
    void startRecording();
  }, [startRecording]);

  return (
    <div className="space-y-4">
      <p className="text-sm text-gov-gray-600 dark:text-dark-muted">
        Graba una nota → STT en Mac mini → respuesta del agente → TTS de vuelta. El audio no va en streaming
        (Whisper y OmniVoice procesan el clip completo). El texto del agente sí puede streamearse en{' '}
        <a href="/playground" className="text-gov-blue-700 dark:text-dark-cyan underline">
          Playground
        </a>{' '}
        con <code className="text-xs">stream=true</code>.
      </p>

      <label className="block text-xs font-semibold text-gov-gray-500">
        Worker
        <input
          className="mt-1 w-full max-w-xs rounded-lg border border-gov-gray-200 dark:border-dark-border bg-white dark:bg-dark-bg px-3 py-2 text-sm"
          value={workerId}
          onChange={(e) => setWorkerId(e.target.value)}
        />
      </label>

      <div className="flex flex-wrap gap-3">
        {!recording ? (
          <button
            type="button"
            onClick={onStart}
            disabled={busy}
            className="inline-flex items-center gap-2 rounded-xl bg-gov-blue-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            <Mic size={18} />
            Grabar
          </button>
        ) : (
          <button
            type="button"
            onClick={() => void sendVoice()}
            className="inline-flex items-center gap-2 rounded-xl bg-red-600 px-4 py-2 text-sm font-semibold text-white"
          >
            <Square size={16} />
            Enviar nota
          </button>
        )}
        {result?.audio_base64 ? (
          <button
            type="button"
            onClick={replayAudio}
            className="inline-flex items-center gap-2 rounded-xl border border-gov-gray-300 dark:border-dark-border px-4 py-2 text-sm font-semibold"
          >
            <Volume2 size={18} />
            Repetir audio
          </button>
        ) : null}
      </div>

      {busy ? <p className="text-sm text-gov-gray-500">Transcribiendo y generando respuesta…</p> : null}
      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {result?.transcription ? (
        <div className="rounded-xl bg-gov-gray-50 dark:bg-dark-bg p-4 text-sm">
          <p className="text-xs font-bold text-gov-gray-500 mb-1">Transcripción</p>
          <p>{result.transcription}</p>
        </div>
      ) : null}

      {result?.response ? (
        <div className="rounded-xl bg-gov-gray-50 dark:bg-dark-bg p-4 text-sm">
          <p className="text-xs font-bold text-gov-gray-500 mb-1">Respuesta</p>
          <p className="whitespace-pre-wrap">{result.response}</p>
          {result.audio_unavailable ? (
            <p className="mt-2 text-xs text-amber-700">Audio no disponible temporalmente (TTS 503).</p>
          ) : null}
          {result.stt_processing_ms != null ? (
            <p className="mt-2 text-xs text-gov-gray-400">
              STT {Math.round(result.stt_processing_ms)} ms
              {result.tts_latency_ms != null ? ` · TTS ${Math.round(result.tts_latency_ms)} ms` : ''}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
