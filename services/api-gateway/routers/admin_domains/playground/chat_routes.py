"""Rutas de chat, voz y cancelación del admin playground."""

from __future__ import annotations

import base64
import logging
import re
import time
from typing import Any

from fastapi import Depends, Request

from routers.admin_domains.admin_common import actor_from_header, problem, require_admin_key
from routers.admin_domains.playground.chat_turn import (
    admin_visual_from_result,
    extract_playground_reply,
    format_playground_chat_payload,
    invoke_playground_chat_sync,
    playground_streaming_response,
    playground_wants_stream,
    prepare_playground_chat_turn,
    prepare_playground_voice_turn,
)
from routers.admin_domains.playground.router import router
from routers.admin_domains.playground.schemas import PlaygroundChatBody, PlaygroundChatCancelBody, PlaygroundVoiceBody


@router.post("/playground/chat", dependencies=[Depends(require_admin_key)])
async def playground_chat(
    body: PlaygroundChatBody,
    request: Request,
    actor: str = Depends(actor_from_header),
):
    """Chat de prueba desde consola admin (exento Tailscale vía prefijo /admin/)."""
    prepared = await prepare_playground_chat_turn(body, actor=actor, request=request)
    if playground_wants_stream(body, request):
        return playground_streaming_response(
            prepared,
            request=request,
            voice_response=bool(body.voice_response),
        )
    result = await invoke_playground_chat_sync(prepared, request=request)
    return format_playground_chat_payload(prepared, result)


@router.post("/playground/voice", dependencies=[Depends(require_admin_key)])
async def playground_voice(
    body: PlaygroundVoiceBody,
    request: Request,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    """
    Round-trip voz: transcribe en Mac mini → invoke agente → opcional TTS de vuelta.
    No usa streaming de audio (Whisper/OmniVoice son inferencia batch).
    """
    from core.sensory_client import (
        SensoryUnavailable,
        resolve_voice_id_for_worker,
        sensory_enabled,
        synthesize_text,
    )
    from core.stt_ingest import SensoryUnavailable as SttDown, process_audio_bytes

    if not sensory_enabled():
        raise problem(503, "DUCKCLAW_SENSORY_BASE_URL no configurado", "sensory")

    try:
        audio_bytes = base64.b64decode((body.audio_base64 or "").strip(), validate=False)
    except Exception as exc:
        raise problem(400, "audio_base64 inválido", str(exc)) from exc
    if not audio_bytes:
        raise problem(400, "audio vacío", "")

    t_stt = time.perf_counter()
    try:
        msg, stt_meta = await process_audio_bytes(
            audio_bytes,
            caption="",
            language_hint=body.language_hint,
        )
    except SttDown as exc:
        raise problem(503, "STT no disponible", str(exc)) from exc
    finally:
        del audio_bytes
    stt_ms = (time.perf_counter() - t_stt) * 1000.0
    transcription = ""
    if "<audio_transcription>" in msg:
        match = re.search(r"<audio_transcription>(.*?)</audio_transcription>", msg, re.DOTALL)
        if match:
            transcription = (match.group(1) or "").strip()

    prepared = await prepare_playground_voice_turn(
        actor=actor,
        worker_id=body.worker_id,
        chat_id=body.chat_id,
        project_id=body.project_id,
        knowledge_scope=body.knowledge_scope,
        msg=msg,
        request=request,
    )
    try:
        result = await invoke_playground_chat_sync(prepared, request=request)
    except Exception as exc:
        raise problem(500, "Error en playground voice (agente)", str(exc)) from exc

    reply = extract_playground_reply(result)

    audio_b64_out: str | None = None
    audio_format_out: str | None = None
    audio_unavailable = False
    tts_ms: float | None = None
    if body.voice_response and reply:
        t_tts = time.perf_counter()
        try:
            voice_id = resolve_voice_id_for_worker(prepared.wid)
            tts_result = await synthesize_text(reply, voice_id)
            audio_b64_out = tts_result.audio_base64
            audio_format_out = tts_result.audio_format
            tts_ms = (time.perf_counter() - t_tts) * 1000.0
            logging.getLogger("duckclaw.gateway.admin_tts").info(
                "voice_batch ok worker=%s format=%s b64_len=%s",
                prepared.wid,
                audio_format_out,
                len(audio_b64_out or ""),
            )
        except SensoryUnavailable:
            audio_unavailable = True

    payload: dict[str, Any] = {
        "ok": True,
        "worker_id": prepared.wid,
        "transcription": transcription,
        "response": reply,
        "audio_base64": audio_b64_out,
        "audio_format": audio_format_out,
        "audio_unavailable": audio_unavailable,
        "stt_processing_ms": stt_meta.get("processing_time_ms") if stt_meta else stt_ms,
        "tts_latency_ms": tts_ms,
        "streaming": {
            "audio_stt": "batch",
            "audio_tts": "batch",
            "agent_text_sse": "/api/v1/admin/playground/chat con stream=true",
        },
    }
    if isinstance(result, dict):
        visual = admin_visual_from_result(prepared.session_id, result, prepared.eff_tenant)
        if visual:
            payload.update(visual)
    return payload


@router.post("/playground/chat/cancel", dependencies=[Depends(require_admin_key)])
async def playground_chat_cancel(body: PlaygroundChatCancelBody) -> dict[str, Any]:
    """Marca interrupción cooperativa para un chat admin en curso (Redis + grafo)."""
    session_id = (body.chat_id or "").strip()
    if not session_id:
        raise problem(400, "chat_id vacío", body.chat_id)
    from duckclaw.graphs.chat_cancel import request_chat_cancel

    ok = request_chat_cancel(session_id)
    try:
        from duckclaw.forge.skills.comfyui_bridge import cancel_comfy_generation_for_chat

        cancel_comfy_generation_for_chat(session_id)
    except Exception:
        pass
    return {"ok": True, "chat_id": session_id, "cancelled": ok}
