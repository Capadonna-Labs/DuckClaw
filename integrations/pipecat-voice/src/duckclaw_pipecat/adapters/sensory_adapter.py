"""
HTTP adapters: Pipecat ↔ Sensory Node (MLX STT/TTS local on Mac mini).

Converts voice segments to PCM/wav payloads for Sensory Node MLX inference on local hardware.
"""

from __future__ import annotations

import base64
import io
import logging
import wave
from collections.abc import AsyncGenerator, Callable

import httpx

_log = logging.getLogger(__name__)


def _require_pipecat_stt():
    from pipecat.frames.frames import ErrorFrame, Frame, TranscriptionFrame
    from pipecat.services.stt_service import SegmentedSTTService
    from pipecat.utils.time import time_now_iso8601

    return SegmentedSTTService, Frame, TranscriptionFrame, ErrorFrame, time_now_iso8601


def _require_pipecat_tts():
    from pipecat.frames.frames import ErrorFrame, Frame, TTSAudioRawFrame
    from pipecat.services.tts_service import TTSService

    return TTSService, Frame, TTSAudioRawFrame, ErrorFrame


class SensorySegmentedSTT:
    """Factory for SegmentedSTTService backed by POST /api/v1/sensory/transcribe."""

    @staticmethod
    def build(*, base_url: str, language_hint: str = "es", timeout_sec: float = 120.0):
        SegmentedSTTService, Frame, TranscriptionFrame, ErrorFrame, time_now_iso8601 = (
            _require_pipecat_stt()
        )
        sensory_url = base_url.rstrip("/")

        class _SensorySTT(SegmentedSTTService):
            def __init__(self) -> None:
                super().__init__()
                self._language_hint = language_hint
                self._timeout = timeout_sec

            async def run_stt(self, audio: bytes) -> AsyncGenerator[Frame | None, None]:
                if not audio:
                    return
                _log.info("sensory STT request bytes=%s", len(audio))
                payload = {
                    "audio_base64": base64.b64encode(audio).decode("ascii"),
                    "language_hint": self._language_hint,
                }
                try:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.post(
                            f"{sensory_url}/api/v1/sensory/transcribe",
                            json=payload,
                        )
                    if response.status_code != 200:
                        detail = (response.text or "")[:240]
                        _log.warning("sensory STT HTTP %s: %s", response.status_code, detail)
                        yield ErrorFrame(error="STT local no disponible")
                        return
                    text = str((response.json() or {}).get("text") or "").strip()
                    if text:
                        yield TranscriptionFrame(
                            text=text,
                            user_id=self._user_id,
                            timestamp=time_now_iso8601(),
                            finalized=True,
                        )
                except Exception as exc:
                    _log.exception("sensory STT failed: %s", exc)
                    yield ErrorFrame(error="STT local falló")

        return _SensorySTT()


class SensoryTTSService:
    """Factory for TTSService backed by POST /api/v1/sensory/synthesize."""

    @staticmethod
    def build(
        *,
        base_url: str,
        resolve_voice_id: Callable[[], str],
        timeout_sec: float = 180.0,
        sample_rate: int = 24000,
        chunk_size: int = 4096,
    ):
        TTSService, Frame, TTSAudioRawFrame, ErrorFrame = _require_pipecat_tts()
        sensory_url = base_url.rstrip("/")

        class _SensoryTTS(TTSService):
            def __init__(self) -> None:
                # Batch HTTP TTS can exceed Pipecat's default 3s stop_frame_timeout_s
                # before the first audio chunk arrives — keep the timeout aligned with HTTP.
                super().__init__(
                    sample_rate=sample_rate,
                    push_start_frame=True,
                    push_stop_frames=True,
                    stop_frame_timeout_s=timeout_sec,
                )
                self._resolve_voice_id = resolve_voice_id
                self._timeout = timeout_sec
                self._chunk_size = chunk_size

            async def run_tts(self, text: str, context_id: str) -> AsyncGenerator[Frame, None]:
                clean = (text or "").strip()
                if not clean:
                    return
                voice_id = (self._resolve_voice_id() or "").strip()
                if not voice_id:
                    yield ErrorFrame(
                        error="voice_id no configurado (DUCKCLAW_TTS_DEFAULT_VOICE_ID / DUCKCLAW_TTS_VOICE_MAP)"
                    )
                    return
                payload = {
                    "text": clean,
                    "voice_id": voice_id,
                    "output_format": "wav",
                }
                try:
                    async with httpx.AsyncClient(timeout=self._timeout) as client:
                        response = await client.post(
                            f"{sensory_url}/api/v1/sensory/synthesize",
                            json=payload,
                        )
                    if response.status_code != 200:
                        detail = (response.text or "")[:240]
                        _log.warning("sensory TTS HTTP %s: %s", response.status_code, detail)
                        yield ErrorFrame(error="TTS local no disponible")
                        return
                    audio_b64 = str((response.json() or {}).get("audio_base64") or "")
                    if not audio_b64:
                        yield ErrorFrame(error="TTS local devolvió audio vacío")
                        return
                    wav_bytes = base64.b64decode(audio_b64)
                    with wave.open(io.BytesIO(wav_bytes), "rb") as wav_file:
                        pcm = wav_file.readframes(wav_file.getnframes())
                        sr = wav_file.getframerate()
                        channels = wav_file.getnchannels()
                    if channels != 1:
                        _log.warning("sensory TTS wav channels=%s; using mono assumption", channels)
                    for offset in range(0, len(pcm), self._chunk_size):
                        chunk = pcm[offset : offset + self._chunk_size]
                        if chunk:
                            yield TTSAudioRawFrame(chunk, sr, 1, context_id=context_id)
                except Exception as exc:
                    _log.exception("sensory TTS failed: %s", exc)
                    yield ErrorFrame(error="TTS local falló")

        return _SensoryTTS()
