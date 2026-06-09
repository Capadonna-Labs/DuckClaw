"""STT ingest — sensory_node over Tailscale, memory-only, Habeas Data."""

from __future__ import annotations

import base64
import logging
from typing import Any

from core.sensory_client import (  # SensoryUnavailable re-exported for Telegram phase
    SensoryUnavailable,
    sensory_enabled,
    transcribe_audio_base64,
)

__all__ = [
    "SensoryUnavailable",
    "enrich_text_with_transcription",
    "is_allowed_audio_mime",
    "process_audio_bytes",
    "stt_down_meta_message",
]

_log = logging.getLogger("duckclaw.gateway.stt_ingest")

_AUDIO_ALLOWED_MIME = frozenset(
    {
        "audio/ogg",
        "audio/mpeg",
        "audio/mp3",
        "audio/wav",
        "audio/x-wav",
        "audio/webm",
        "application/ogg",
    }
)


def is_allowed_audio_mime(mime: str) -> bool:
    m = (mime or "").strip().lower()
    if not m:
        return True
    if m in _AUDIO_ALLOWED_MIME:
        return True
    return m.startswith("audio/")


def enrich_text_with_transcription(
    *,
    caption: str,
    transcription: str,
    from_reply: bool = False,
) -> str:
    cap = (caption or "").strip()
    tx = (transcription or "").strip()
    prefix = "Usuario dice: " if cap else ""
    reply_note = " (transcripción de audio en mensaje respondido)" if from_reply else ""
    parts: list[str] = []
    if cap:
        parts.append(f"{prefix}{cap}")
    if tx:
        parts.append(f"<audio_transcription>{tx}</audio_transcription>{reply_note}")
    return "\n\n".join(parts).strip()


async def process_audio_bytes(
    audio_bytes: bytes,
    *,
    caption: str = "",
    language_hint: str | None = "es",
    from_reply: bool = False,
) -> tuple[str, dict[str, Any] | None]:
    """
    Transcribe audio via sensory_node and return enriched text for the agent.

    Returns (enriched_text, meta_dict). On failure raises SensoryUnavailable.
    """
    if not sensory_enabled():
        raise SensoryUnavailable("sensory not configured")
    b64 = base64.b64encode(audio_bytes).decode("ascii")
    try:
        result = await transcribe_audio_base64(b64, language_hint=language_hint)
    finally:
        del audio_bytes
        del b64

    enriched = enrich_text_with_transcription(
        caption=caption,
        transcription=result.text,
        from_reply=from_reply,
    )
    meta = {
        "processing_time_ms": result.processing_time_ms,
        "language_detected": result.language_detected,
    }
    _log.info(
        "stt_ingest ok lang=%s ms=%.1f text_len=%s",
        result.language_detected,
        result.processing_time_ms,
        len(result.text or ""),
    )
    return enriched, meta


def stt_down_meta_message(*, audio_only: bool) -> str:
    if audio_only:
        return (
            "[META: SENSORY_STT_DOWN] El usuario envió un mensaje de voz; la transcripción no está "
            "disponible (sensory_node inactivo o error de red Tailscale). Pide que reenvíe el mensaje "
            "en texto."
        )
    return (
        "[META: SENSORY_STT_DOWN] El audio adjunto no pudo transcribirse; se procesará solo el caption "
        "si existe."
    )
