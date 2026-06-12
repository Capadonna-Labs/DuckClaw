/** Reproduce TTS base64 — singleton en DOM (requerido en Chrome Android). */

export type TtsAudioFormat = 'ogg' | 'wav';

const SILENT_WAV_B64 =
  'UklGRigAAABXQVZFZm10IBAAAAABAAEARKwAAIhYAQACABAAZGF0YQQAAAAAAA==';

let audioPrimed = false;
let domAudio: HTMLAudioElement | null = null;
let domAudioUrl: string | null = null;

function isIOSDevice(): boolean {
  if (typeof navigator === 'undefined') return false;
  return (
    /iPad|iPhone|iPod/.test(navigator.userAgent) ||
    (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
  );
}

function ensureDomAudio(): HTMLAudioElement {
  if (typeof document === 'undefined') {
    throw new Error('no_document');
  }
  if (!domAudio) {
    const el = document.createElement('audio');
    el.setAttribute('playsinline', '');
    el.setAttribute('preload', 'auto');
    el.style.display = 'none';
    document.body.appendChild(el);
    domAudio = el;
  }
  return domAudio;
}

function revokeDomAudioUrl(): void {
  if (domAudioUrl) {
    URL.revokeObjectURL(domAudioUrl);
    domAudioUrl = null;
  }
}

function stopDomAudio(): void {
  if (!domAudio) return;
  domAudio.pause();
  domAudio.removeAttribute('src');
  domAudio.load();
  revokeDomAudioUrl();
}

/** Desbloquea reproducción tras gesto del usuario (enviar mensaje/voz o botón). */
export function primeAudioPlayback(): void {
  if (audioPrimed || typeof window === 'undefined') return;
  try {
    const audio = ensureDomAudio();
    audio.volume = 1;
    audio.muted = false;
    audio.src = `data:audio/wav;base64,${SILENT_WAV_B64}`;
    void audio.play().then(() => {
      audioPrimed = true;
      audio.pause();
      audio.removeAttribute('src');
      audio.load();
    });
  } catch {
    /* ignore */
  }
}

export function sniffTtsAudioFormat(base64: string): TtsAudioFormat {
  try {
    const sample = (base64 || '').slice(0, 48);
    if (!sample) return 'ogg';
    const bin = atob(sample);
    if (bin.startsWith('OggS')) return 'ogg';
    if (bin.startsWith('RIFF')) return 'wav';
  } catch {
    /* ignore */
  }
  return 'ogg';
}

export function ttsAudioMime(format: TtsAudioFormat): string {
  return format === 'wav' ? 'audio/wav' : 'audio/ogg';
}

function base64ToBlob(base64: string, mime: string): Blob {
  const bin = atob(base64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return new Blob([bytes], { type: mime });
}

export type PlayTtsAudioResult =
  | { ok: true }
  | { ok: false; reason: string; mime: string; isIOS: boolean };

async function loadAudioSrc(
  audio: HTMLAudioElement,
  src: string,
  mime: string,
  isIOS: boolean
): Promise<{ mediaError: string | null; duration: number; strategy: string }> {
  return new Promise((resolve) => {
    const timer = window.setTimeout(() => {
      resolve({
        mediaError: null,
        duration: Number.isFinite(audio.duration) ? audio.duration : 0,
        strategy: 'timeout',
      });
    }, 8000);

    audio.onerror = () => {
      window.clearTimeout(timer);
      const code = audio.error?.code ?? 0;
      const msg = audio.error?.message ?? 'media_element_error';
      resolve({
        mediaError: `media_error:${code}:${msg}`,
        duration: 0,
        strategy: 'error',
      });
    };

    audio.onloadedmetadata = () => {
      window.clearTimeout(timer);
      resolve({
        mediaError: null,
        duration: Number.isFinite(audio.duration) ? audio.duration : 0,
        strategy: isIOS ? 'blob' : 'blob',
      });
    };

    audio.src = src;
    audio.load();
  });
}

export async function playTtsAudio(
  base64: string,
  opts?: { format?: TtsAudioFormat; source?: string }
): Promise<PlayTtsAudioResult> {
  void opts;
  const trimmed = (base64 || '').trim();
  if (!trimmed) {
    return { ok: false, reason: 'empty_base64', mime: '', isIOS: false };
  }

  const format = sniffTtsAudioFormat(trimmed);
  const mime = ttsAudioMime(format);
  const isIOS = isIOSDevice();

  stopDomAudio();
  const audio = ensureDomAudio();
  audio.volume = 1;
  audio.muted = false;

  const blob = base64ToBlob(trimmed, mime);
  revokeDomAudioUrl();
  domAudioUrl = URL.createObjectURL(blob);

  let loadResult = await loadAudioSrc(audio, domAudioUrl, mime, isIOS);

  if (loadResult.mediaError) {
    revokeDomAudioUrl();
    const dataSrc = `data:${mime};base64,${trimmed}`;
    loadResult = await loadAudioSrc(audio, dataSrc, mime, isIOS);
  }

  if (loadResult.mediaError) {
    stopDomAudio();
    return { ok: false, reason: loadResult.mediaError, mime, isIOS };
  }

  try {
    await audio.play();
    audio.onended = () => stopDomAudio();
    return { ok: true };
  } catch (e) {
    stopDomAudio();
    const reason = e instanceof Error ? e.name : 'play_failed';
    return { ok: false, reason, mime, isIOS };
  }
}

export function stopTtsPlayback(): void {
  stopDomAudio();
}
