"""Resolución de session_id y cancelación de tareas de chat en vuelo."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import Request

from core.models import ChatRequest


def resolve_chat_session_id(body: ChatRequest, req: Request) -> tuple[str, str]:
    """
    Identificador de hilo para estado por chat (sandbox, /team, auditoría).

    Orden: cuerpo JSON (chat_id y alias Pydantic) → query ?chat_id= / ?session_id=
    → cabeceras X-Chat-Id, X-Session-Id, X-Duckclaw-Chat-Id.
    """
    cid = (body.chat_id or "").strip()
    if cid:
        return cid, "body.chat_id"
    for key in ("chat_id", "session_id", "thread_id", "chatId"):
        raw = req.query_params.get(key)
        if raw and str(raw).strip():
            return str(raw).strip(), f"query.{key}"
    for header in ("X-Chat-Id", "X-Session-Id", "X-Duckclaw-Chat-Id"):
        raw = req.headers.get(header)
        if raw and str(raw).strip():
            return str(raw).strip(), f"header.{header}"
    return "default", "default"


async def abort_chat_invoke_task(session_id: str, invoke_task: asyncio.Task[Any]) -> None:
    from duckclaw.graphs.chat_cancel import request_chat_cancel

    request_chat_cancel(session_id)
    try:
        from duckclaw.forge.skills.comfyui_bridge import cancel_comfy_generation_for_chat

        cancel_comfy_generation_for_chat(session_id)
    except Exception:
        pass
    if not invoke_task.done():
        invoke_task.cancel()
        try:
            await invoke_task
        except Exception:
            pass
