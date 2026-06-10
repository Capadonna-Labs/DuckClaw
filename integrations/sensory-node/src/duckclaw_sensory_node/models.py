"""Pydantic contracts for sensory_node API."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VoiceId = Literal["campus_legal_main", "leila_assistant", "finanz_alert", "quant_trader_brief"]

_FORBIDDEN_TTS_REFERENCE_FIELDS = frozenset(
    {
        "ref_audio",
        "reference_audio",
        "ref_text",
        "reference_text",
        "ref_tokens",
        "voice_embedding",
        "speaker_embedding",
    }
)


class STTRequest(BaseModel):
    audio_base64: str = Field(..., description="Audio codificado en base64 (OGG/WAV/MP3)")
    language_hint: str | None = Field("es", description="Hint de idioma para MLX-Whisper")


class STTResponse(BaseModel):
    text: str
    processing_time_ms: float
    language_detected: str


class TTSRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., max_length=3000, description="Texto a sintetizar")
    voice_id: VoiceId = Field(
        ...,
        description="ID del vector de voz pre-aprobado (Identity Lock)",
    )
    speed: float = Field(1.0, ge=0.5, le=2.0)
    output_format: Literal["ogg", "wav"] = Field(
        default="ogg",
        description="ogg (Telegram) o wav (Safari/iOS en admin UI)",
    )

    @classmethod
    def reject_reference_injection(cls, payload: dict) -> None:
        """Raise ValueError if payload attempts dynamic voice reference injection."""
        for key in payload:
            if key in _FORBIDDEN_TTS_REFERENCE_FIELDS:
                raise ValueError(f"reference field forbidden: {key}")


class TTSResponse(BaseModel):
    audio_base64: str = Field(..., description="Audio sintetizado (OGG/Opus o WAV)")
    duration_sec: float
    latency_ms: float
    audio_format: Literal["ogg", "wav"] = "ogg"
