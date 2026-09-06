"""Streaming SSE para POST /api/v1/agent/*/chat con stream=true."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import HTTPException, Request

from core.chat_session import abort_chat_invoke_task
from core.chat_visual_artifacts import admin_visual_fields_from_invoke_result
from core.models import ChatRequest
from core.sse_stream import (
    emit_chat_reply_sse,
    friendly_chat_error_message,
    sse_audio,
    sse_comment,
    sse_error,
    sse_heartbeat,
    sse_terminal_done,
)

_gateway_log = logging.getLogger("duckclaw.gateway")


async def invoke_chat_sse_body(
    payload: ChatRequest,
    worker_id: str,
    session_id: str,
    tenant_id: str,
    *,
    http_request: Request | None = None,
    invoke_chat: Any,
    **invoke_kwargs: Any,
):
    """Generador SSE: invoca el grafo, heartbeats admin en vivo y tokens + [DONE]."""
    from core.admin_chat_heartbeat import iter_admin_heartbeats
    from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session

    redis_client = invoke_kwargs.get("redis_client")
    voice_response = bool(invoke_kwargs.pop("voice_response", False))
    admin_session = is_admin_ui_chat_session(session_id)
    stop = asyncio.Event()
    heartbeat_task: asyncio.Task | None = None
    heartbeat_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def _pump_admin_heartbeats() -> None:
        try:
            async for item in iter_admin_heartbeats(redis_client, session_id, stop=stop):
                await heartbeat_queue.put(item)
        except asyncio.CancelledError:
            raise

    if admin_session and redis_client is not None:
        heartbeat_task = asyncio.create_task(_pump_admin_heartbeats())

    invoke_task = asyncio.create_task(
        invoke_chat(
            payload,
            worker_id,
            session_id,
            tenant_id,
            **invoke_kwargs,
        )
    )
    client_detached = False
    last_sse_at = time.monotonic()
    keepalive_s = 25.0

    try:
        from duckclaw.graphs.chat_cancel import is_chat_cancel_requested

        while not invoke_task.done():
            if http_request is not None and await http_request.is_disconnected():
                if admin_session:
                    # ponytail: no cancelar invoke_worker anidado si el proxy SSE corta; el cliente recarga historial.
                    client_detached = True
                    _gateway_log.info(
                        "admin SSE client disconnected chat_id=%r; invoke continues detached",
                        session_id,
                    )
                    break
                await abort_chat_invoke_task(session_id, invoke_task)
                yield sse_error("Interrumpido por el usuario.")
                yield sse_terminal_done()
                return
            if is_chat_cancel_requested(session_id):
                await abort_chat_invoke_task(session_id, invoke_task)
                yield sse_error("Interrumpido por el usuario.")
                yield sse_terminal_done()
                return
            try:
                hb = await asyncio.wait_for(heartbeat_queue.get(), timeout=0.2)
                yield sse_heartbeat(
                    str(hb.get("text") or ""),
                    kind=str(hb.get("kind") or "status"),
                    worker_id=str(hb.get("worker_id") or "") or None,
                    swarm_slot=hb.get("swarm_slot"),
                    artifact_id=str(hb.get("artifact_id") or "").strip() or None,
                    artifact_tenant_id=str(hb.get("artifact_tenant_id") or "").strip() or None,
                    tool_name=str(hb.get("tool_name") or "").strip() or None,
                    tool_phase=str(hb.get("tool_phase") or "").strip().lower() or None,
                    tool_detail=str(hb.get("tool_detail") or "").strip() or None,
                    elapsed_ms=hb.get("elapsed_ms"),
                )
                last_sse_at = time.monotonic()
            except asyncio.TimeoutError:
                if time.monotonic() - last_sse_at >= keepalive_s:
                    yield sse_comment("keepalive")
                    last_sse_at = time.monotonic()
                continue

        if client_detached:
            return

        while not heartbeat_queue.empty():
            hb = heartbeat_queue.get_nowait()
            yield sse_heartbeat(
                str(hb.get("text") or ""),
                kind=str(hb.get("kind") or "status"),
                worker_id=str(hb.get("worker_id") or "") or None,
                swarm_slot=hb.get("swarm_slot"),
                artifact_id=str(hb.get("artifact_id") or "").strip() or None,
                artifact_tenant_id=str(hb.get("artifact_tenant_id") or "").strip() or None,
                tool_name=str(hb.get("tool_name") or "").strip() or None,
                tool_phase=str(hb.get("tool_phase") or "").strip().lower() or None,
                tool_detail=str(hb.get("tool_detail") or "").strip() or None,
                elapsed_ms=hb.get("elapsed_ms"),
            )

        result = await invoke_task
        reply = ""
        assigned: str | None = None
        usage: dict[str, Any] | None = None
        elapsed_ms: int | None = None
        sse_extra: dict[str, Any] | None = None
        if isinstance(result, dict):
            reply = str(result.get("response") or result.get("reply") or "")
            assigned = result.get("assigned_worker_id") or result.get("worker_id")
            usage = result.get("usage_tokens")
            raw_elapsed = result.get("elapsed_ms")
            if raw_elapsed is not None:
                try:
                    elapsed_ms = int(raw_elapsed)
                except (TypeError, ValueError):
                    elapsed_ms = None
            admin_visual = admin_visual_fields_from_invoke_result(session_id, result, tenant_id)
            sse_extra: dict[str, Any] = {}
            if admin_visual:
                sse_extra.update(admin_visual)
            ctx_est = result.get("context_estimated_tokens")
            if isinstance(ctx_est, (int, float)) and ctx_est >= 0:
                sse_extra["context_estimated_tokens"] = int(ctx_est)
        else:
            reply = str(result or "")
        want_tts = voice_response and bool((reply or "").strip())
        async for event in emit_chat_reply_sse(
            reply,
            assigned_worker_id=assigned,
            usage_tokens=usage,
            worker_id=worker_id,
            elapsed_ms=elapsed_ms,
            extra=sse_extra,
            emit_terminal=not want_tts,
        ):
            yield event
        if want_tts:
            from core.sensory_client import (
                SensoryUnavailable,
                resolve_voice_id_for_worker,
                sensory_enabled,
                synthesize_text,
                tts_snippet_for_reply,
            )

            eff_worker = (assigned or worker_id or "").strip() or worker_id
            if sensory_enabled():
                snippet = tts_snippet_for_reply(reply)
                if snippet:
                    try:
                        voice_id = resolve_voice_id_for_worker(eff_worker)
                        tts_result = await synthesize_text(snippet, voice_id)
                        _gateway_log.getChild("admin_tts").info(
                            "sse_audio ok worker=%s format=%s b64_len=%s",
                            eff_worker,
                            tts_result.audio_format,
                            len(tts_result.audio_base64 or ""),
                        )
                        yield sse_audio(
                            audio_base64=tts_result.audio_base64,
                            audio_format=tts_result.audio_format,
                        )
                    except SensoryUnavailable as exc:
                        _gateway_log.getChild("admin_tts").warning(
                            "sse_audio unavailable worker=%s: %s", eff_worker, exc
                        )
                        yield sse_audio(audio_unavailable=True)
                    except Exception as exc:
                        _gateway_log.getChild("admin_tts").warning(
                            "sse_audio failed worker=%s: %s", eff_worker, exc
                        )
                        yield sse_audio(audio_unavailable=True)
                else:
                    yield sse_audio(audio_unavailable=True)
            else:
                yield sse_audio(audio_unavailable=True)
            yield sse_terminal_done()
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        yield sse_error(detail, status_hint=exc.status_code)
        yield sse_terminal_done()
    except Exception as exc:
        yield sse_error(friendly_chat_error_message(exc))
        yield sse_terminal_done()
    finally:
        stop.set()
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        if not invoke_task.done() and not client_detached:
            await abort_chat_invoke_task(session_id, invoke_task)
