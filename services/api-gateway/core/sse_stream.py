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


def sse_heartbeat(
    text: str,
    *,
    kind: str = "status",
    worker_id: str | None = None,
    swarm_slot: int | None = None,
) -> str:
    meta: dict[str, Any] = {"type": "heartbeat", "text": text, "kind": kind}
    wid = (worker_id or "").strip()
    if wid:
        meta["worker_id"] = wid
    if swarm_slot is not None:
        meta["swarm_slot"] = max(1, int(swarm_slot))
    return sse_data(meta)


def sse_error(message: str, *, status_hint: int | None = None) -> str:
    err: dict[str, Any] = {"type": "error", "message": message}
    if status_hint is not None:
        err["status"] = status_hint
    return sse_data(err)


def sse_terminal_done() -> str:
    return "data: [DONE]\n\n"


def friendly_chat_error_message(exc: BaseException) -> str:
    """Mensaje legible para la UI admin cuando falla inferencia local."""
    msg = str(exc).strip() or exc.__class__.__name__
    low = msg.lower()
    if "connection refused" in low or "errno 61" in low:
        if "8080" in msg or ":8080" in low:
            return (
                f"{msg}\n\n"
                "MLX texto (puerto 8080) no responde. En PM2 suele faltar «MLX-Inference»; "
                "solo «MLX-Vision» escucha en 8081. Arranca el servidor mlx_lm en 8080 "
                "(p. ej. `pm2 start` del ecosystem MLX) o usa `/model provider=deepseek`."
            )
        return (
            f"{msg}\n\n"
            "No hay servidor de inferencia en la URL configurada. "
            "Revisa MLX_PORT / OPENAI_API_BASE en .env del gateway o cambia de proveedor con /model."
        )
    if "apiconnectionerror" in low or "connecterror" in low:
        return (
            f"{msg}\n\n"
            "Error de conexión al proveedor LLM. Comprueba que el servicio esté en marcha "
            "o cambia proveedor con `/model`."
        )
    return msg


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
    elapsed_ms: int | None = None,
    chunk_chars: int = 12,
    delay_s: float = 0.018,
) -> AsyncIterator[str]:
    """Genera eventos SSE token a token y cierre [DONE]."""
    extra: dict[str, Any] | None = None
    if elapsed_ms is not None:
        extra = {"elapsed_ms": int(elapsed_ms)}
    async for piece in stream_text_chunks(reply, chunk_chars=chunk_chars, delay_s=delay_s):
        yield sse_token(piece)
    yield sse_done(
        response=reply,
        assigned_worker_id=assigned_worker_id,
        usage_tokens=usage_tokens,
        worker_id=worker_id,
        extra=extra,
    )
    yield sse_terminal_done()
