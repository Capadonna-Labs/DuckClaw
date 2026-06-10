"""
Proxy REST hacia sensory_node en Mac mini (Tailscale).

El gateway VPS expone la misma interfaz que el microservicio edge para admin,
playground y clientes HTTP sin acoplar Telegram en esta fase.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from core.sensory_client import (
    SensoryError,
    SensoryForbidden,
    SensoryUnavailable,
    sensory_enabled,
    sensory_health,
    synthesize_text,
    transcribe_audio_base64,
)

_log = logging.getLogger("duckclaw.gateway.sensory")

router = APIRouter(prefix="/api/v1/sensory", tags=["sensory"])

VoiceId = Literal["campus_legal_main", "leila_assistant", "finanz_alert", "quant_trader_brief"]


class STTRequest(BaseModel):
    audio_base64: str = Field(..., description="Audio base64 (OGG/WAV/MP3)")
    language_hint: str | None = Field("es", description="Hint de idioma")


class STTResponse(BaseModel):
    text: str
    processing_time_ms: float
    language_detected: str


class TTSRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., max_length=3000)
    voice_id: VoiceId
    speed: float = Field(1.0, ge=0.5, le=2.0)


class TTSResponse(BaseModel):
    audio_base64: str
    duration_sec: float
    latency_ms: float


def _require_sensory_configured() -> None:
    if not sensory_enabled():
        raise HTTPException(
            status_code=503,
            detail="DUCKCLAW_SENSORY_BASE_URL not configured",
        )


def _map_sensory_error(exc: SensoryError) -> HTTPException:
    if isinstance(exc, SensoryForbidden):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, SensoryUnavailable):
        return HTTPException(status_code=503, detail=str(exc))
    return HTTPException(status_code=502, detail=str(exc))


@router.get("/health")
async def sensory_health_proxy() -> dict[str, Any]:
    _require_sensory_configured()
    data = await sensory_health()
    if data is None:
        raise HTTPException(status_code=503, detail="sensory_node unreachable")
    return data


@router.post("/transcribe", response_model=STTResponse)
async def sensory_transcribe(body: STTRequest) -> STTResponse:
    _require_sensory_configured()
    try:
        result = await transcribe_audio_base64(
            body.audio_base64,
            language_hint=body.language_hint,
        )
    except SensoryError as exc:
        raise _map_sensory_error(exc) from exc
    return STTResponse(
        text=result.text,
        processing_time_ms=result.processing_time_ms,
        language_detected=result.language_detected,
    )


@router.post("/synthesize", response_model=TTSResponse)
async def sensory_synthesize(body: TTSRequest) -> TTSResponse:
    _require_sensory_configured()
    try:
        result = await synthesize_text(
            body.text,
            body.voice_id,
            speed=body.speed,
        )
    except SensoryError as exc:
        raise _map_sensory_error(exc) from exc
    return TTSResponse(
        audio_base64=result.audio_base64,
        duration_sec=result.duration_sec,
        latency_ms=result.latency_ms,
    )
