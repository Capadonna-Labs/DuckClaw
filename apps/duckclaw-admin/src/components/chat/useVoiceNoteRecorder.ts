'use client';

import { useCallback, useEffect, useRef, useState } from 'react';

type VoiceNoteRecorder = {
  recording: boolean;
  busy: boolean;
  error: string | null;
  setBusy: (busy: boolean) => void;
  setError: (error: string | null) => void;
  startRecording: () => Promise<void>;
  stopAndGetBase64: () => Promise<string>;
};

function pickSupportedMimeType(): string | undefined {
  if (typeof MediaRecorder === 'undefined') return undefined;
  const candidates = ['audio/webm;codecs=opus', 'audio/webm', 'audio/ogg;codecs=opus', 'audio/mp4'];
  return candidates.find((candidate) => MediaRecorder.isTypeSupported(candidate));
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error('No se pudo leer la nota de voz'));
    reader.onloadend = () => {
      const result = typeof reader.result === 'string' ? reader.result : '';
      resolve(result.split(',', 2)[1] || '');
    };
    reader.readAsDataURL(blob);
  });
}

export function useVoiceNoteRecorder(): VoiceNoteRecorder {
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);

  const cleanup = useCallback(() => {
    recorderRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    chunksRef.current = [];
    setRecording(false);
  }, []);

  useEffect(() => cleanup, [cleanup]);

  const startRecording = useCallback(async () => {
    if (recording) return;
    setError(null);
    if (
      typeof navigator === 'undefined' ||
      !navigator.mediaDevices?.getUserMedia ||
      typeof MediaRecorder === 'undefined'
    ) {
      setError('La grabación de voz no está disponible en este navegador');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mimeType = pickSupportedMimeType();
      const recorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (event) => {
        if (event.data.size > 0) chunksRef.current.push(event.data);
      };
      recorderRef.current = recorder;
      streamRef.current = stream;
      recorder.start();
      setRecording(true);
    } catch (err) {
      cleanup();
      setError(err instanceof Error ? err.message : 'No se pudo iniciar la grabación de voz');
    }
  }, [cleanup, recording]);

  const stopAndGetBase64 = useCallback(async () => {
    const recorder = recorderRef.current;
    if (!recorder || recorder.state === 'inactive') {
      cleanup();
      return '';
    }
    setError(null);
    return new Promise<string>((resolve) => {
      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: recorder.mimeType || 'audio/webm' });
        cleanup();
        if (blob.size === 0) {
          resolve('');
          return;
        }
        blobToBase64(blob)
          .then(resolve)
          .catch((err) => {
            setError(err instanceof Error ? err.message : 'No se pudo procesar la nota de voz');
            resolve('');
          });
      };
      recorder.stop();
    });
  }, [cleanup]);

  return {
    recording,
    busy,
    error,
    setBusy,
    setError,
    startRecording,
    stopAndGetBase64,
  };
}
