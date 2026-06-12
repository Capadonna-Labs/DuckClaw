'use client';

import { useCallback, useRef, useState } from 'react';

function mediaEnvironment() {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') {
    return {
      hasNavigator: false,
      hasMediaDevices: false,
      isSecureContext: false,
      protocol: '',
      hostname: '',
    };
  }
  return {
    hasNavigator: true,
    hasMediaDevices: Boolean(navigator.mediaDevices?.getUserMedia),
    isSecureContext: window.isSecureContext,
    protocol: window.location.protocol,
    hostname: window.location.hostname,
  };
}

function microphoneUnavailableMessage(env: ReturnType<typeof mediaEnvironment>): string {
  if (!env.isSecureContext || env.protocol === 'http:') {
    return (
      'El micrófono requiere HTTPS. Abre el admin por la URL Tailscale ' +
      '(https://<tu-servidor>.ts.net:8443/) en lugar de http://IP:3000.'
    );
  }
  if (!env.hasMediaDevices) {
    return 'Este navegador no expone acceso al micrófono (mediaDevices no disponible).';
  }
  return 'No se pudo acceder al micrófono.';
}

function pickAudioMimeType(): string {
  const candidates = [
    'audio/webm;codecs=opus',
    'audio/webm',
    'audio/ogg;codecs=opus',
    'audio/mp4',
    'audio/aac',
  ];
  for (const mime of candidates) {
    if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(mime)) {
      return mime;
    }
  }
  return '';
}

export function blobToBase64(blob: Blob): Promise<string> {
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

function arrayBufferToBase64(buffer: ArrayBuffer): string {
  const bytes = new Uint8Array(buffer);
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    const slice = bytes.subarray(i, i + chunk);
    for (let j = 0; j < slice.length; j++) {
      binary += String.fromCharCode(slice[j]);
    }
  }
  return btoa(binary);
}

function encodeWavFromAudioBuffer(audioBuffer: AudioBuffer): ArrayBuffer {
  const channelData = audioBuffer.getChannelData(0);
  const length = channelData.length;
  const sampleRate = audioBuffer.sampleRate;
  const buffer = new ArrayBuffer(44 + length * 2);
  const view = new DataView(buffer);
  const writeString = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  };
  writeString(0, 'RIFF');
  view.setUint32(4, 36 + length * 2, true);
  writeString(8, 'WAVE');
  writeString(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(36, 'data');
  view.setUint32(40, length * 2, true);
  let offset = 44;
  for (let i = 0; i < length; i++) {
    const s = Math.max(-1, Math.min(1, channelData[i]));
    view.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    offset += 2;
  }
  return buffer;
}

/** Convierte WebM/MP4 del navegador a WAV base64 (compatible con Whisper en Mac). */
export async function blobToWavBase64(blob: Blob): Promise<string> {
  const arrayBuffer = await blob.arrayBuffer();
  const audioContext = new AudioContext();
  try {
    const audioBuffer = await audioContext.decodeAudioData(arrayBuffer.slice(0));
    return arrayBufferToBase64(encodeWavFromAudioBuffer(audioBuffer));
  } finally {
    await audioContext.close();
  }
}

export function useVoiceNoteRecorder() {
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mediaRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const mimeRef = useRef<string>('audio/webm');

  const releaseStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }, []);

  const cancelRecording = useCallback(() => {
    const rec = mediaRef.current;
    if (rec && rec.state !== 'inactive') {
      rec.onstop = () => {
        releaseStream();
      };
      rec.stop();
    } else {
      releaseStream();
    }
    mediaRef.current = null;
    chunksRef.current = [];
    setRecording(false);
  }, [releaseStream]);

  const startRecording = useCallback(async () => {
    setError(null);
    const env = mediaEnvironment();
    if (!env.hasMediaDevices) {
      setError(microphoneUnavailableMessage(env));
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const mime = pickAudioMimeType();
      mimeRef.current = mime || 'audio/webm';
      const rec = new MediaRecorder(stream, mime ? { mimeType: mime } : undefined);
      chunksRef.current = [];
      rec.ondataavailable = (ev) => {
        if (ev.data.size > 0) chunksRef.current.push(ev.data);
      };
      mediaRef.current = rec;
      rec.start(250);
      setRecording(true);
    } catch (e) {
      releaseStream();
      const errName = e instanceof DOMException ? e.name : e instanceof Error ? e.name : 'unknown';
      const rawMsg = e instanceof Error ? e.message : 'No se pudo acceder al micrófono';
      const errMsg =
        errName === 'NotAllowedError' || /permission denied/i.test(rawMsg)
          ? 'Permiso de micrófono denegado. En el navegador: Ajustes del sitio → Micrófono → Permitir, y recarga.'
          : rawMsg;
      setError(errMsg);
    }
  }, [releaseStream]);

  const stopAndGetBase64 = useCallback(async (): Promise<string | null> => {
    const rec = mediaRef.current;
    if (!rec || rec.state === 'inactive') {
      setError('Graba una nota de voz primero');
      return null;
    }

    return new Promise<string | null>((resolve) => {
      const finalize = async () => {
        const chunks = [...chunksRef.current];
        chunksRef.current = [];
        mediaRef.current = null;
        releaseStream();
        setRecording(false);

        const totalBytes = chunks.reduce((sum, c) => sum + c.size, 0);

        if (!chunks.length || totalBytes === 0) {
          setError('No se capturó audio. Mantén pulsado el micrófono 2–3 s y vuelve a intentar.');
          resolve(null);
          return;
        }
        const blob = new Blob(chunks, { type: chunks[0]?.type || mimeRef.current });
        try {
          let b64: string;
          try {
            b64 = await blobToWavBase64(blob);
          } catch {
            b64 = await blobToBase64(blob);
          }
          setError(null);
          resolve(b64);
        } catch {
          setError('No se pudo procesar el audio grabado');
          resolve(null);
        }
      };

      rec.onstop = () => {
        void finalize();
      };
      try {
        if (rec.state === 'recording' && typeof rec.requestData === 'function') {
          rec.requestData();
        }
        rec.stop();
      } catch {
        void finalize();
      }
    });
  }, [releaseStream]);

  return {
    recording,
    busy,
    setBusy,
    error,
    setError,
    startRecording,
    stopAndGetBase64,
    cancelRecording,
  };
}
