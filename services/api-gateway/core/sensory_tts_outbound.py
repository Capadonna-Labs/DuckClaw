"""TTS outbound — synthesize agent reply and send Telegram voice with graceful degradation."""

from __future__ import annotations

import base64
import logging
import os

from core.sensory_client import (
    SensoryUnavailable,
    resolve_voice_id_for_worker,
    sensory_enabled,
    synthesize_text,
)
from core.telegram_media_upload import send_voice_to_telegram_sync

_log = logging.getLogger("duckclaw.gateway.sensory_tts_outbound")

_AUDIO_UNAVAILABLE_NOTE = "Audio no disponible temporalmente."


def _tts_enabled() -> bool:
    if not sensory_enabled():
        return False
    return (os.environ.get("DUCKCLAW_TTS_OUTBOUND_ENABLED") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _tts_snippet(text: str) -> str:
    """First paragraph or chunk for TTS (max 1500)."""
    t = (text or "").strip()
    if not t:
        return t
    para = t.split("\n\n", 1)[0].strip()
    if len(para) > 1500:
        return para[:1500]
    return para


async def maybe_send_tts_voice_reply(
    *,
    bot_token: str,
    chat_id: str | int,
    reply_plain: str,
    worker_id: str,
) -> tuple[bool, str | None]:
    """
    Attempt TTS + sendVoice. Returns (voice_sent, degradation_suffix).

    degradation_suffix is appended to text reply when TTS fails (503).
    """
    if not _tts_enabled():
        return False, None
    snippet = _tts_snippet(reply_plain)
    if not snippet:
        return False, None
    voice_id = resolve_voice_id_for_worker(worker_id)
    try:
        result = await synthesize_text(snippet, voice_id)
    except SensoryUnavailable as exc:
        _log.warning("tts outbound unavailable worker=%s voice=%s: %s", worker_id, voice_id, exc)
        return False, _AUDIO_UNAVAILABLE_NOTE
    except Exception as exc:  # noqa: BLE001
        _log.warning("tts outbound failed worker=%s: %s", worker_id, exc)
        return False, _AUDIO_UNAVAILABLE_NOTE

    try:
        ogg_bytes = base64.b64decode(result.audio_base64, validate=False)
    except Exception:
        return False, _AUDIO_UNAVAILABLE_NOTE
    ok = send_voice_to_telegram_sync(
        bot_token=bot_token,
        chat_id=str(chat_id),
        voice_bytes=ogg_bytes,
    )
    if ok:
        _log.info("tts voice sent chat_id=%s voice_id=%s latency_ms=%.1f", chat_id, voice_id, result.latency_ms)
        return True, None
    return False, _AUDIO_UNAVAILABLE_NOTE
