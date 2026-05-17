"""Utilidades SSE (text/event-stream) para chat en streaming."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any


def sse_data(payload: str | dict[str, Any]) -> str:
    """Un evento SSE: ``data: …\\n\\n``."""
    if isinstance(payload, dict):
        body = json.dumps(payload, ensure_ascii=False)
    else:
        body = payload
    return f"data: {body}\n\n"


def sse_token(content: str) -> str:
    return sse_data({"type": "token", "content": content})


def sse_done(
    *,
    response: str = "",
    assigned_worker_id: str | None = None,
    usage_tokens: dict[str, Any] | None = None,
    worker_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> str:
    meta: dict[str, Any] = {"type": "done", "response": response}
    if assigned_worker_id:
        meta["assigned_worker_id"] = assigned_worker_id
    if usage_tokens:
        meta["usage_tokens"] = usage_tokens
    if worker_id:
        meta["worker_id"] = worker_id
    if extra:
        meta.update(extra)
    return sse_data(meta)


def sse_error(message: str, *, status_hint: int | None = None) -> str:
    err: dict[str, Any] = {"type": "error", "message": message}
    if status_hint is not None:
        err["status"] = status_hint
    return sse_data(err)


def sse_terminal_done() -> str:
    return "data: [DONE]\n\n"


SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


async def stream_text_chunks(
    text: str,
    *,
    chunk_chars: int = 12,
    delay_s: float = 0.018,
) -> AsyncIterator[str]:
    """
    Trocea texto para simular escritura progresiva (hasta que el grafo exponga astream nativo).
    Respeta saltos de línea y espacios cuando es posible.
    """
    import asyncio

    if not text:
        return
    i = 0
    n = len(text)
    while i < n:
        end = min(i + chunk_chars, n)
        if end < n and text[end] not in (" ", "\n"):
            space = text.find(" ", end, min(end + 8, n))
            if space != -1:
                end = space + 1
        chunk = text[i:end]
        if chunk:
            yield chunk
            if delay_s > 0:
                await asyncio.sleep(delay_s)
        i = end


async def emit_chat_reply_sse(
    reply: str,
    *,
    assigned_worker_id: str | None = None,
    usage_tokens: dict[str, Any] | None = None,
    worker_id: str | None = None,
    chunk_chars: int = 12,
    delay_s: float = 0.018,
) -> AsyncIterator[str]:
    """Genera eventos SSE token a token y cierre [DONE]."""
    async for piece in stream_text_chunks(reply, chunk_chars=chunk_chars, delay_s=delay_s):
        yield sse_token(piece)
    yield sse_done(
        response=reply,
        assigned_worker_id=assigned_worker_id,
        usage_tokens=usage_tokens,
        worker_id=worker_id,
    )
    yield sse_terminal_done()
