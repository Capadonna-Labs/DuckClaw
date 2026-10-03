"""Voice I/O: ElevenLabs (when ELEVENLABS_API_KEY is set) or the Mac mini sensory_node.

ElevenLabs runs from the gateway itself (Scribe STT + TTS), so voice notes no longer
depend on the Mac mini being up. DUCKCLAW_VOICE_PROVIDER=sensory forces the old path.
"""

from __future__ import annotations

import base64
import io
import logging
import os
import re
import time
import wave
from typing import Any

import httpx
from pydantic import BaseModel

_log = logging.getLogger("duckclaw.gateway.sensory_client")


class SensoryError(Exception):
    """Base sensory client error."""


class SensoryUnavailable(SensoryError):
    """503, timeout, or connect failure — gateway should degrade gracefully."""


class SensoryForbidden(SensoryError):
    """403 Identity Lock violation."""


class STTResult(BaseModel):
    text: str
    processing_time_ms: float
    language_detected: str


class TTSResult(BaseModel):
    audio_base64: str
    duration_sec: float
    latency_ms: float
    audio_format: str = "ogg"


def _sensory_base_url() -> str:
    for key in ("DUCKCLAW_SENSORY_BASE_URL", "SENSORY_BASE_URL"):
        v = (os.environ.get(key) or "").strip().rstrip("/")
        if v:
            return v
    return ""


def _elevenlabs_key() -> str:
    if (os.environ.get("DUCKCLAW_VOICE_PROVIDER") or "").strip().lower() == "sensory":
        return ""
    return (os.environ.get("ELEVENLABS_API_KEY") or "").strip()


def sensory_enabled() -> bool:
    return bool(_elevenlabs_key() or _sensory_base_url())


_ELEVENLABS_API = "https://api.elevenlabs.io/v1"
_ELEVENLABS_PCM_RATE = 22050
_elevenlabs_voice_cache: dict[str, Any] = {}


async def _elevenlabs_voices(key: str) -> list[dict[str, Any]]:
    """Account voices (cached 10 min); also the health probe for the key."""
    hit = _elevenlabs_voice_cache.get("voices")
    if hit and time.monotonic() - hit[0] < 600:
        return hit[1]
    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        r = await client.get(f"{_ELEVENLABS_API}/voices", headers={"xi-api-key": key})
    if r.status_code != 200:
        raise _map_http_error(503 if r.status_code >= 500 else r.status_code, r.text[:300])
    voices = [v for v in (r.json().get("voices") or []) if isinstance(v, dict)]
    _elevenlabs_voice_cache["voices"] = (time.monotonic(), voices)
    return voices


async def _elevenlabs_voice_id(key: str, requested: str) -> str:
    """Worker map / env voice, else the first voice of the account."""
    vid = (requested or "").strip()
    if vid and vid != "default":
        return vid
    env_vid = (os.environ.get("DUCKCLAW_ELEVENLABS_VOICE_ID") or "").strip()
    if env_vid:
        return env_vid
    voices = await _elevenlabs_voices(key)
    if not voices:
        raise SensoryUnavailable("ElevenLabs: la cuenta no tiene voces")
    return str(voices[0].get("voice_id") or "")


def _pcm_to_wav(pcm: bytes, rate: int) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


async def _elevenlabs_transcribe(key: str, audio_b64: str, language_hint: str | None) -> STTResult:
    t0 = time.monotonic()
    audio = base64.b64decode(audio_b64, validate=False)
    data = {"model_id": (os.environ.get("DUCKCLAW_ELEVENLABS_STT_MODEL") or "scribe_v1").strip()}
    if language_hint:
        data["language_code"] = language_hint
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(_stt_timeout())) as client:
            r = await client.post(
                f"{_ELEVENLABS_API}/speech-to-text",
                headers={"xi-api-key": key},
                data=data,
                files={"file": ("audio", audio, "application/octet-stream")},
            )
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise SensoryUnavailable(str(exc)) from exc
    if r.status_code != 200:
        raise _map_http_error(503 if r.status_code >= 500 else r.status_code, r.text[:300])
    body = r.json()
    return STTResult(
        text=str(body.get("text") or "").strip(),
        processing_time_ms=(time.monotonic() - t0) * 1000,
        language_detected=str(body.get("language_code") or language_hint or ""),
    )


async def _elevenlabs_synthesize(key: str, text: str, voice_id: str, speed: float) -> TTSResult:
    # ponytail: always WAV (raw PCM wrapped with stdlib). Telegram voice notes want
    # OGG/Opus; add an ffmpeg/opus step when that path is switched to ElevenLabs.
    t0 = time.monotonic()
    vid = await _elevenlabs_voice_id(key, voice_id)
    payload: dict[str, Any] = {
        "text": (text or "")[:_TTS_TEXT_MAX_LEN],
        "model_id": (os.environ.get("DUCKCLAW_ELEVENLABS_TTS_MODEL") or "eleven_flash_v2_5").strip(),
    }
    if speed and abs(speed - 1.0) > 1e-3:
        payload["voice_settings"] = {"speed": max(0.7, min(1.2, float(speed)))}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(_tts_timeout())) as client:
            r = await client.post(
                f"{_ELEVENLABS_API}/text-to-speech/{vid}",
                params={"output_format": f"pcm_{_ELEVENLABS_PCM_RATE}"},
                headers={"xi-api-key": key},
                json=payload,
            )
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise SensoryUnavailable(str(exc)) from exc
    if r.status_code != 200:
        raise _map_http_error(503 if r.status_code >= 500 else r.status_code, r.text[:300])
    pcm = r.content
    return TTSResult(
        audio_base64=base64.b64encode(_pcm_to_wav(pcm, _ELEVENLABS_PCM_RATE)).decode("ascii"),
        duration_sec=len(pcm) / (2 * _ELEVENLABS_PCM_RATE),
        latency_ms=(time.monotonic() - t0) * 1000,
        audio_format="wav",
    )


def _stt_timeout() -> float:
    try:
        return float(os.environ.get("DUCKCLAW_SENSORY_TIMEOUT_STT") or "30.0")
    except ValueError:
        return 30.0


def _tts_timeout() -> float:
    try:
        return float(os.environ.get("DUCKCLAW_SENSORY_TIMEOUT_TTS") or "90.0")
    except ValueError:
        return 90.0


_TTS_TEXT_MAX_LEN = 3000
_BUILTIN_VOICE_MAP: dict[str, str] = {}
_WORKER_INSTANCE_HEADER_RE = re.compile(
    r"^[\w.-]+\s+\d+\s*[·•]\s*[^\n]*(?:\n|$)",
    re.IGNORECASE | re.MULTILINE,
)
_HRULE_RE = re.compile(r"^---+\s*$", re.MULTILINE)


def _map_http_error(status: int, detail: str) -> SensoryError:
    if status == 403:
        return SensoryForbidden(detail or "forbidden")
    if status in (503, 504):
        return SensoryUnavailable(detail or "unavailable")
    return SensoryError(detail or f"HTTP {status}")


async def transcribe_audio_base64(
    audio_b64: str,
    *,
    language_hint: str | None = "es",
) -> STTResult:
    key = _elevenlabs_key()
    if key:
        return await _elevenlabs_transcribe(key, audio_b64, language_hint)
    base = _sensory_base_url()
    if not base:
        raise SensoryUnavailable("DUCKCLAW_SENSORY_BASE_URL not configured")
    url = f"{base}/api/v1/sensory/transcribe"
    payload = {"audio_base64": audio_b64, "language_hint": language_hint or "es"}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(_stt_timeout())) as client:
            r = await client.post(url, json=payload)
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise SensoryUnavailable(str(exc)) from exc
    if r.status_code != 200:
        detail = ""
        try:
            detail = str(r.json().get("detail") or "")
        except Exception:
            detail = r.text[:500]
        raise _map_http_error(r.status_code, detail)
    data = r.json()
    return STTResult.model_validate(data)


def tts_snippet_for_reply(text: str) -> str:
    """Prepare agent reply for TTS: drop admin headers; sanitize/cap on sensory_node."""
    t = (text or "").strip()
    if not t:
        return ""
    t = _WORKER_INSTANCE_HEADER_RE.sub("", t, count=1)
    t = _HRULE_RE.sub("", t)
    t = re.sub(r"^[\w.-]+\s+\d+\s*\n", "", t, flags=re.IGNORECASE)
    return t.strip()


def _admin_tts_output_format() -> str:
    raw = (os.environ.get("DUCKCLAW_ADMIN_TTS_FORMAT") or "wav").strip().lower()
    return raw if raw in ("ogg", "wav") else "wav"


async def synthesize_text(
    text: str,
    voice_id: str,
    *,
    speed: float = 1.0,
    output_format: str | None = None,
) -> TTSResult:
    key = _elevenlabs_key()
    if key:
        return await _elevenlabs_synthesize(key, text, voice_id, speed)
    base = _sensory_base_url()
    if not base:
        raise SensoryUnavailable("DUCKCLAW_SENSORY_BASE_URL not configured")
    url = f"{base}/api/v1/sensory/synthesize"
    fmt = (output_format or _admin_tts_output_format()).strip().lower()
    if fmt not in ("ogg", "wav"):
        fmt = "wav"
    payload: dict[str, Any] = {
        "text": (text or "")[:_TTS_TEXT_MAX_LEN],
        "voice_id": voice_id,
        "speed": speed,
        "output_format": fmt,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(_tts_timeout())) as client:
            r = await client.post(url, json=payload)
            if r.status_code == 422 and fmt == "wav":
                payload.pop("output_format", None)
                r = await client.post(url, json=payload)
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        raise SensoryUnavailable(str(exc)) from exc
    if r.status_code != 200:
        detail = ""
        try:
            detail = str(r.json().get("detail") or "")
        except Exception:
            detail = r.text[:500]
        raise _map_http_error(r.status_code, detail)
    return TTSResult.model_validate(r.json())


def resolve_voice_id_for_worker(worker_id: str) -> str:
    """Map worker_id → pre-approved voice_id via DUCKCLAW_TTS_VOICE_MAP JSON."""
    import json

    default = (os.environ.get("DUCKCLAW_TTS_DEFAULT_VOICE_ID") or "default").strip() or "default"
    wid = (worker_id or "").strip()
    raw = (os.environ.get("DUCKCLAW_TTS_VOICE_MAP") or "").strip()
    mapping: dict[str, Any] = dict(_BUILTIN_VOICE_MAP)
    if raw:
        try:
            mapping.update(json.loads(raw))
        except json.JSONDecodeError:
            _log.warning("invalid DUCKCLAW_TTS_VOICE_MAP JSON")
    if wid in mapping:
        return str(mapping[wid])
    if "default" in mapping:
        return str(mapping["default"])
    return default


async def sensory_health() -> dict[str, Any] | None:
    key = _elevenlabs_key()
    if key:
        try:
            voices = await _elevenlabs_voices(key)
        except Exception as exc:  # bad key / no voices_read permission
            _log.warning("elevenlabs health failed: %s", exc)
            return None
        return {"ok": True, "provider": "elevenlabs", "tts_loaded": True, "stt_loaded": True, "voices": len(voices)}
    base = _sensory_base_url()
    if not base:
        return None
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
            r = await client.get(f"{base}/health")
            if r.status_code == 200:
                return r.json()
    except Exception:
        return None
    return None
