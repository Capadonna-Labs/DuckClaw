/**
 * WebRTC mic via native getUserMedia (no AudioWorklet on capture path).
 * Bot audio plays from the remote WebRTC track in the browser.
 */
import type { PipecatClientOptions, RTVIEventCallbacks, Tracks } from '@pipecat-ai/client-js';

type MediaManagerLike = {
  setUserAudioCallback: (cb: (data: ArrayBuffer) => void) => void;
  setClientOptions: (options: PipecatClientOptions, override?: boolean) => void;
  initialize: () => Promise<void>;
  connect: () => Promise<void>;
  disconnect: () => Promise<void>;
  userStartedSpeaking: () => Promise<unknown>;
  bufferBotAudio: (data: ArrayBuffer | Int16Array, id?: string) => Int16Array | undefined;
  getAllMics: () => Promise<MediaDeviceInfo[]>;
  getAllCams: () => Promise<MediaDeviceInfo[]>;
  getAllSpeakers: () => Promise<MediaDeviceInfo[]>;
  updateMic: (micId: string) => void | Promise<void>;
  updateCam: (camId: string) => void;
  updateSpeaker: (speakerId: string) => void | Promise<void>;
  selectedMic: MediaDeviceInfo | Record<string, never>;
  selectedCam: MediaDeviceInfo | Record<string, never>;
  selectedSpeaker: MediaDeviceInfo | Record<string, never>;
  enableMic: (enable: boolean) => void | Promise<void>;
  enableCam: (enable: boolean) => void;
  enableScreenShare: (enable: boolean) => void;
  isCamEnabled: boolean;
  isMicEnabled: boolean;
  isSharingScreen: boolean;
  tracks: () => Tracks;
  supportsScreenShare: boolean;
  ensureLiveMic?: () => Promise<MediaStreamTrack | null>;
};

export type NativeWebRtcMediaManager = MediaManagerLike;

export function createNativeWebRtcMediaManager(): NativeWebRtcMediaManager {
  let micStream: MediaStream | null = null;
  let micEnabled = true;
  let initialized = false;
  let callbacks: RTVIEventCallbacks = {};
  let selectedMic: MediaDeviceInfo | Record<string, never> = {};

  async function ensureMicStream(deviceId?: string, force = false): Promise<MediaStream> {
    const existingTrack = micStream?.getAudioTracks()[0];
    const requestedId =
      deviceId ||
      (typeof selectedMic === 'object' && 'deviceId' in selectedMic
        ? selectedMic.deviceId
        : undefined);
    if (
      !force &&
      existingTrack?.readyState === 'live' &&
      (!requestedId || existingTrack.getSettings().deviceId === requestedId)
    ) {
      existingTrack.enabled = micEnabled;
      return micStream!;
    }
    if (micStream) {
      micStream.getTracks().forEach((track) => track.stop());
      micStream = null;
    }
    const audio: boolean | MediaTrackConstraints = deviceId
      ? { deviceId: { exact: deviceId } }
      : true;
    micStream = await navigator.mediaDevices.getUserMedia({ audio, video: false });
    const track = micStream.getAudioTracks()[0];
    if (track) {
      track.enabled = micEnabled;
      const devices = await navigator.mediaDevices.enumerateDevices();
      const match = devices.find((d) => d.deviceId === track.getSettings().deviceId);
      if (match) selectedMic = match;
      callbacks.onTrackStarted?.(track);
    }
    return micStream;
  }

  const manager: MediaManagerLike = {
    supportsScreenShare: false,

    setUserAudioCallback() {
      /* server-side STT uses WebRTC audio; no local PCM callback */
    },

    setClientOptions(options: PipecatClientOptions, override?: boolean) {
      if (override || !callbacks) {
        callbacks = options.callbacks ?? {};
      }
      micEnabled = options.enableMic !== false;
    },

    async initialize() {
      initialized = true;
    },

    async connect() {
      if (!initialized) await manager.initialize();
      await ensureMicStream(
        typeof selectedMic === 'object' && 'deviceId' in selectedMic
          ? selectedMic.deviceId
          : undefined
      );
    },

    async disconnect() {
      if (micStream) {
        micStream.getTracks().forEach((track) => {
          callbacks.onTrackStopped?.(track);
          track.stop();
        });
        micStream = null;
      }
      initialized = false;
    },

    async userStartedSpeaking() {
      return undefined;
    },

    bufferBotAudio() {
      return undefined;
    },

    async getAllMics() {
      const devices = await navigator.mediaDevices.enumerateDevices();
      return devices.filter((d) => d.kind === 'audioinput');
    },

    async getAllCams() {
      return [];
    },

    async getAllSpeakers() {
      const devices = await navigator.mediaDevices.enumerateDevices();
      return devices.filter((d) => d.kind === 'audiooutput');
    },

    async updateMic(micId: string) {
      await ensureMicStream(micId || undefined);
    },

    updateCam() {},

    updateSpeaker() {},

    get selectedMic() {
      return selectedMic;
    },

    get selectedCam() {
      return {};
    },

    get selectedSpeaker() {
      return {};
    },

    async enableMic(enable: boolean) {
      micEnabled = enable;
      micStream?.getAudioTracks().forEach((track) => {
        track.enabled = enable;
      });
    },

    enableCam() {},

    enableScreenShare() {},

    get isCamEnabled() {
      return false;
    },

    get isMicEnabled() {
      return micEnabled;
    },

    get isSharingScreen() {
      return false;
    },

    tracks(): Tracks {
      const audioTrack = micStream?.getAudioTracks()[0];
      return {
        local: audioTrack ? { audio: audioTrack } : {},
      };
    },

    async ensureLiveMic(): Promise<MediaStreamTrack | null> {
      await ensureMicStream(undefined, true);
      return micStream?.getAudioTracks()[0] ?? null;
    },
  };

  return manager;
}

const AUDIO_TRANSCEIVER_INDEX = 0;

/**
 * Push a fresh local mic track onto the active SmallWebRTC peer connection.
 * Renegotiation can end the original getUserMedia track while the sender still
 * references it; replaceTrack is required for audio to reach DuckClaw-Voice.
 */
export async function replaceLocalAudioOnSmallWebRtcTransport(
  transport: unknown,
  audioTrack: MediaStreamTrack | null | undefined
): Promise<boolean> {
  if (!audioTrack || audioTrack.readyState !== 'live') return false;
  const peerConnection = (transport as { pc?: RTCPeerConnection | null }).pc;
  if (!peerConnection) return false;
  const audioSender = peerConnection.getTransceivers()[AUDIO_TRANSCEIVER_INDEX]?.sender;
  if (!audioSender) return false;
  await audioSender.replaceTrack(audioTrack);
  return true;
}
