'use client';

import { useCallback, useRef, useState } from 'react';
import { Mic, Square, Volume2 } from 'lucide-react';

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

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => {
      const dataUrl = String(reader.result || '');
      const b64 = dataUrl.includes(',') ? dataUrl.split(',')[1] : dataUrl;
      resolve(b64);
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(blob);
  });
}

export function VoiceLabPanel() {
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<VoiceResult | null>(null);
  const [workerId, setWorkerId] = useState('default');
  const mediaRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const stopRecording = useCallback(() => {
    const rec = mediaRef.current;
    if (rec && rec.state !== 'inactive') {
      rec.stop();
    }
    mediaRef.current = null;
    setRecording(false);
  }, []);

  const startRecording = useCallback(async () => {
    setError(null);
    setResult(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime =
        MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
          ? 'audio/webm;codecs=opus'
          : MediaRecorder.isTypeSupported('audio/ogg;codecs=opus')
            ? 'audio/ogg;codecs=opus'
            : '';
      const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunksRef.current = [];
      rec.ondataavailable = (ev) => {
        if (ev.data.size > 0) chunksRef.current.push(ev.data);
      };
      rec.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
      };
      mediaRef.current = rec;
      rec.start();
      setRecording(true);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'No se pudo acceder al micrófono');
    }
  }, []);

  const sendVoice = useCallback(async () => {
    stopRecording();
    const chunks = chunksRef.current;
    if (!chunks.length) {
      setError('Graba una nota de voz primero');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const blob = new Blob(chunks, { type: chunks[0]?.type || 'audio/webm' });
      const audio_base64 = await blobToBase64(blob);
      const res = await fetch('/api/admin/playground/voice', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
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
        throw new Error(data.detail || `HTTP ${res.status}`);
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
      chunksRef.current = [];
    }
  }, [stopRecording, workerId]);

  const replayAudio = useCallback(() => {
    if (!result?.audio_base64) return;
    const audio = new Audio(`data:audio/ogg;base64,${result.audio_base64}`);
    void audio.play();
  }, [result]);

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
            onClick={() => void startRecording()}
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
