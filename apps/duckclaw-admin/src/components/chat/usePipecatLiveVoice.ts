'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { PipecatClient, RTVIEvent } from '@pipecat-ai/client-js';
import {
  SmallWebRTCTransport,
  type SmallWebRTCTransportConstructorOptions,
} from '@pipecat-ai/small-webrtc-transport';
import { mutationHeaders } from '@/lib/csrfClient';
import {
  createNativeWebRtcMediaManager,
  replaceLocalAudioOnSmallWebRtcTransport,
  type NativeWebRtcMediaManager,
} from '@/lib/nativeWebRtcMediaManager';

export type LiveVoiceStatus = 'idle' | 'connecting' | 'connected' | 'disconnecting' | 'error';

export type LiveVoiceSpeakingPhase = 'idle' | 'user' | 'bot' | 'graph';

export type VoiceAppState = {
  chat_id: string;
  worker_id: string;
  tenant_id: string;
  vault_path?: string;
  section?: string;
  variant: 'playground' | 'bubble';
};

type SmallWebRtcTransportOptions = SmallWebRTCTransportConstructorOptions;

type UsePipecatLiveVoiceOptions = {
  enabled?: boolean;
  onDisconnected?: () => void;
  onGraphPhaseChange?: (phase: LiveVoiceSpeakingPhase) => void;
};

function formatElapsed(seconds: number): string {
  const mm = Math.floor(seconds / 60)
    .toString()
    .padStart(2, '0');
  const ss = (seconds % 60).toString().padStart(2, '0');
  return `${mm}:${ss}`;
}

function parseUpdateStatePayload(payload: unknown): LiveVoiceSpeakingPhase | null {
  if (!payload || typeof payload !== 'object') return null;
  const record = payload as Record<string, unknown>;
  const inner =
    record.type === 'update_state'
      ? record
      : typeof record.data === 'object' && record.data
        ? (record.data as Record<string, unknown>)
        : record;
  if (inner.type !== 'update_state') return null;
  return inner.phase === 'graph_invoke' ? 'graph' : 'idle';
}

async function formatLiveVoiceConnectError(error: unknown): Promise<string> {
  if (error instanceof Response) {
    let detail = '';
    try {
      const payload = (await error.clone().json()) as { detail?: string; info?: string };
      detail = (payload.detail || payload.info || '').trim();
    } catch {
      detail = '';
    }
    return detail || `Señalización WebRTC HTTP ${error.status}`;
  }
  if (typeof error === 'string' && error.trim()) return error.trim();
  if (error instanceof Error && error.message.trim()) return error.message.trim();
  if (error == null) return 'Conexión WebRTC interrumpida';
  return 'No se pudo iniciar voz en vivo';
}

export function usePipecatLiveVoice({
  enabled = true,
  onDisconnected,
  onGraphPhaseChange,
}: UsePipecatLiveVoiceOptions = {}) {
  const [status, setStatus] = useState<LiveVoiceStatus>('idle');
  const [speakingPhase, setSpeakingPhase] = useState<LiveVoiceSpeakingPhase>('idle');
  const [error, setError] = useState<string | null>(null);
  const [elapsedLabel, setElapsedLabel] = useState('00:00');
  const [userSubtitle, setUserSubtitle] = useState('');
  const [botSubtitle, setBotSubtitle] = useState('');

  const clientRef = useRef<PipecatClient | null>(null);
  const timerRef = useRef<number | null>(null);
  const startedAtRef = useRef<number>(0);
  const appStateRef = useRef<VoiceAppState | null>(null);
  const localMicTrackIdRef = useRef<string | null>(null);
  const botAudioRef = useRef<HTMLAudioElement | null>(null);
  const onDisconnectedRef = useRef(onDisconnected);
  const onGraphPhaseChangeRef = useRef(onGraphPhaseChange);

  onDisconnectedRef.current = onDisconnected;
  onGraphPhaseChangeRef.current = onGraphPhaseChange;

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const startTimer = useCallback(() => {
    clearTimer();
    startedAtRef.current = Date.now();
    setElapsedLabel('00:00');
    timerRef.current = window.setInterval(() => {
      const seconds = Math.floor((Date.now() - startedAtRef.current) / 1000);
      setElapsedLabel(formatElapsed(seconds));
    }, 1000);
  }, [clearTimer]);

  const sendAppState = useCallback((appState: VoiceAppState) => {
    appStateRef.current = appState;
    const client = clientRef.current;
    if (!client) return;
    client.sendClientMessage('app_state', appState);
  }, []);

  const endCall = useCallback(async () => {
    clearTimer();
    setStatus((prev) => (prev === 'idle' ? 'idle' : 'disconnecting'));
    const client = clientRef.current;
    clientRef.current = null;
    if (client) {
      try {
        await client.disconnect();
      } catch {
        /* ignore teardown errors */
      }
    }
    botAudioRef.current?.pause();
    botAudioRef.current = null;
    localMicTrackIdRef.current = null;
    setSpeakingPhase('idle');
    setUserSubtitle('');
    setBotSubtitle('');
    setError(null);
    setStatus('idle');
    onDisconnectedRef.current?.();
  }, [clearTimer]);

  const startCall = useCallback(
    async (appState: VoiceAppState) => {
      if (!enabled) {
        setError('Voz en vivo no disponible');
        return;
      }
      if (status === 'connecting' || status === 'connected') return;

      setError(null);
      setStatus('connecting');
      setUserSubtitle('');
      setBotSubtitle('');
      setSpeakingPhase('idle');

      try {
        const nativeMediaManager = createNativeWebRtcMediaManager();

        const offerParams = new URLSearchParams({
          worker_id: appState.worker_id,
          chat_id: appState.chat_id,
          tenant_id: appState.tenant_id,
        });
        const offerEndpoint = `/api/admin/playground/voice/realtime/offer?${offerParams.toString()}`;
        const csrfHeaders = mutationHeaders('POST');

        const client = new PipecatClient({
          transport: new SmallWebRTCTransport({
            mediaManager:
              nativeMediaManager as NonNullable<SmallWebRtcTransportOptions['mediaManager']>,
          }),
          enableMic: true,
          enableCam: false,
          callbacks: {
            onTrackStarted: (track) => {
              if (track.kind !== 'audio') return;
              const localTrack = nativeMediaManager.tracks().local?.audio;
              if (localTrack && track.id === localTrack.id) {
                localMicTrackIdRef.current = track.id;
                return;
              }
              if (localMicTrackIdRef.current && track.id === localMicTrackIdRef.current) return;
              const botAudio = document.createElement('audio');
              botAudio.autoplay = true;
              botAudio.srcObject = new MediaStream([track]);
              botAudioRef.current = botAudio;
              void botAudio.play().catch(() => {});
            },
            onUserTranscript: (data) => {
              const text = (data.text || '').trim();
              if (text) setUserSubtitle(text);
            },
            onBotTranscript: (data) => {
              const text = (data.text || '').trim();
              if (text) setBotSubtitle(text);
            },
            onUserStartedSpeaking: () => setSpeakingPhase('user'),
            onUserStoppedSpeaking: () =>
              setSpeakingPhase((prev) => (prev === 'user' ? 'idle' : prev)),
            onBotStartedSpeaking: () => setSpeakingPhase('bot'),
            onBotStoppedSpeaking: () =>
              setSpeakingPhase((prev) => (prev === 'bot' ? 'idle' : prev)),
            onServerMessage: (payload) => {
              const phase = parseUpdateStatePayload(payload);
              if (phase === 'graph') {
                setSpeakingPhase('graph');
                onGraphPhaseChangeRef.current?.('graph');
              } else if (phase === 'idle') {
                setSpeakingPhase('idle');
                onGraphPhaseChangeRef.current?.('idle');
              }
            },
          },
        });

        client.on(RTVIEvent.Error, (payload) => {
          const detail =
            payload && typeof payload === 'object' && 'message' in payload
              ? String((payload as { message?: unknown }).message || '')
              : '';
          if (/TTS local/i.test(detail)) {
            setError('Audio local no disponible; revisa DUCKCLAW_TTS_VOICE_MAP en DuckClaw-Voice.');
            setStatus('error');
            return;
          }
          setError('Error en la sesión de voz en vivo');
          setStatus('error');
        });

        clientRef.current = client;
        appStateRef.current = appState;

        const connectParams = {
          webrtcRequestParams: {
            endpoint: offerEndpoint,
            headers: new Headers(csrfHeaders),
          },
          iceConfig: {
            iceServers: [{ urls: 'stun:stun.l.google.com:19302' }],
          },
        };

        const connectDeadlineMs = 45_000;
        await Promise.race([
          client.connect(connectParams),
          new Promise<never>((_, reject) => {
            window.setTimeout(
              () => reject(new Error('Tiempo de espera agotado al conectar voz en vivo')),
              connectDeadlineMs
            );
          }),
        ]);

        // Renegotiation can end the first mic track; acquire a fresh one and re-attach.
        const mediaManagerWithRevive = nativeMediaManager as NativeWebRtcMediaManager;
        let revivedMicTrack: MediaStreamTrack | null = null;
        if (mediaManagerWithRevive.ensureLiveMic) {
          revivedMicTrack = await mediaManagerWithRevive.ensureLiveMic();
        }
        await replaceLocalAudioOnSmallWebRtcTransport(
          client.transport,
          revivedMicTrack ?? nativeMediaManager.tracks().local?.audio
        );
        try {
          client.enableMic(true);
        } catch {
          /* transport may already have mic attached */
        }

        const localMicTrack = nativeMediaManager.tracks().local?.audio;
        if (localMicTrack) localMicTrackIdRef.current = localMicTrack.id;
        if (!localMicTrack || localMicTrack.readyState === 'ended') {
          throw new Error(
            'El micrófono se desconectó durante la señalización WebRTC. Intenta de nuevo.'
          );
        }

        client.sendClientMessage('app_state', appState);
        startTimer();
        setStatus('connected');
      } catch (e) {
        clientRef.current = null;
        const msg = await formatLiveVoiceConnectError(e);
        setError(msg);
        setStatus('error');
      }
    },
    [enabled, startTimer, status]
  );

  const toggleCall = useCallback(
    async (appState: VoiceAppState) => {
      if (status === 'connected' || status === 'connecting') {
        await endCall();
        return;
      }
      if (status === 'error') {
        await endCall();
      }
      await startCall(appState);
    },
    [endCall, startCall, status]
  );

  useEffect(() => {
    return () => {
      void endCall();
    };
  }, [endCall]);

  return {
    status,
    speakingPhase,
    error,
    elapsedLabel,
    userSubtitle,
    botSubtitle,
    isActive: status === 'connected' || status === 'connecting',
    isConnected: status === 'connected',
    startCall,
    endCall,
    toggleCall,
    sendAppState,
  };
}

export type PipecatLiveVoiceController = ReturnType<typeof usePipecatLiveVoice>;
