"""HTTP client to Mac mini sensory_node over Tailscale."""

from __future__ import annotations

import logging
import os
import re
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


def sensory_enabled() -> bool:
    return bool(_sensory_base_url())


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
_BUILTIN_VOICE_MAP: dict[str, str] = {
    "quant-trader": "finanz_alert",
    "quant_trader": "finanz_alert",
    "Quant-Trader": "finanz_alert",
    "finanz": "finanz_alert",
}
_QUANT_HEADER_RE = re.compile(
    r"^(?:quant[- ]?trader|Quant-Trader)\s+\d+\s*[·•]\s*[^\n]*(?:\n|$)",
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
    t = _QUANT_HEADER_RE.sub("", t, count=1)
    t = _HRULE_RE.sub("", t)
    t = re.sub(r"^(?:quant[- ]?trader)\s+\d+\s*\n", "", t, flags=re.IGNORECASE)
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

    default = "leila_assistant"
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
