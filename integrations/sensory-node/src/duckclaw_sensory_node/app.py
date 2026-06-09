"""FastAPI application factory."""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError

from duckclaw_sensory_node.audio_io import decode_audio_base64
from duckclaw_sensory_node.concurrency import acquire_inference_slot, release_inference_slot
from duckclaw_sensory_node.engines.stt import STTEngine
from duckclaw_sensory_node.engines.tts import TTSEngine
from duckclaw_sensory_node.health import build_health_payload
from duckclaw_sensory_node.middleware import TailscaleOnlyMiddleware
from duckclaw_sensory_node.models import STTRequest, STTResponse, TTSRequest, TTSResponse
from duckclaw_sensory_node.sanitize import sanitize_tts_text

_log = logging.getLogger("duckclaw.sensory")

_stt = STTEngine()
_tts = TTSEngine()


async def _inference_guard() -> AsyncIterator[None]:
    await acquire_inference_slot()
    try:
        yield
    finally:
        release_inference_slot()


@asynccontextmanager
async def lifespan(app: FastAPI):
    _log.info("warming sensory models")
    try:
        await asyncio.to_thread(_stt.warm)
    except Exception as exc:
        _log.error("STT warm failed: %s", exc)
    try:
        await asyncio.to_thread(_tts.warm)
    except Exception as exc:
        _log.error("TTS warm failed: %s", exc)
    yield
    _log.info("sensory shutdown")


def create_app() -> FastAPI:
    app = FastAPI(title="DuckClaw Sensory Node", version="0.1.0", lifespan=lifespan)
    app.add_middleware(TailscaleOnlyMiddleware)

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return build_health_payload(stt_loaded=_stt.loaded, tts_loaded=_tts.loaded)

    @app.post("/api/v1/sensory/transcribe", response_model=STTResponse)
    async def transcribe(body: STTRequest, _: None = Depends(_inference_guard)) -> STTResponse:
        try:
            audio, sr = decode_audio_base64(body.audio_base64)
            result = await asyncio.to_thread(
                _stt.transcribe,
                audio,
                sr,
                language_hint=body.language_hint,
            )
            return STTResponse(
                text=result["text"],
                processing_time_ms=result["processing_time_ms"],
                language_detected=result["language_detected"],
            )
        except Exception as exc:
            _log.warning("transcribe failed: %s: %s", type(exc).__name__, exc)
            msg = str(exc).strip()
            detail = f"STT inference failed: {type(exc).__name__}"
            if msg:
                detail = f"{detail}: {msg[:240]}"
            raise HTTPException(status_code=503, detail=detail) from exc

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_request, exc: RequestValidationError):
        from starlette.responses import JSONResponse

        for err in exc.errors():
            loc = err.get("loc") or ()
            if any(
                str(part) in ("ref_audio", "reference_audio", "ref_text", "ref_tokens", "voice_embedding")
                for part in loc
            ):
                return JSONResponse(status_code=403, content={"detail": "reference field forbidden"})
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    @app.post("/api/v1/sensory/synthesize", response_model=TTSResponse)
    async def synthesize(body: TTSRequest, _: None = Depends(_inference_guard)) -> TTSResponse:
        if not _tts.has_voice(body.voice_id):
            raise HTTPException(status_code=403, detail=f"voice_id not approved: {body.voice_id}")

        clean = sanitize_tts_text(body.text)
        if not clean:
            raise HTTPException(status_code=400, detail="text empty after sanitization")

        try:
            result = await asyncio.to_thread(
                _tts.synthesize,
                clean,
                body.voice_id,
                speed=body.speed,
                output_format=body.output_format,
            )
            return TTSResponse(
                audio_base64=result["audio_base64"],
                duration_sec=result["duration_sec"],
                latency_ms=result["latency_ms"],
                audio_format=result.get("audio_format") or body.output_format,
            )
        except TimeoutError as exc:
            raise HTTPException(status_code=503, detail="TTS inference timeout or OOM") from exc
        except Exception as exc:
            _log.warning("synthesize failed voice=%s err=%s", body.voice_id, type(exc).__name__)
            raise HTTPException(status_code=503, detail="TTS inference timeout or OOM") from exc

    return app
