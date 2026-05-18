"""Tests utilidades SSE del API Gateway."""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

_gw = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
if str(_gw) not in sys.path:
    sys.path.insert(0, str(_gw))

from core.sse_stream import emit_chat_reply_sse, sse_done, sse_terminal_done, sse_token  # noqa: E402


def test_emit_chat_reply_sse_tokens_and_done():
    async def _run() -> list[str]:
        out: list[str] = []
        async for ev in emit_chat_reply_sse("Hola mundo", chunk_chars=20, delay_s=0):
            out.append(ev)
        return out

    events = asyncio.run(_run())
    assert any('"token"' in e for e in events)
    assert sse_terminal_done() in events
    parts: list[str] = []
    for e in events:
        if not e.startswith("data: {"):
            continue
        payload = json.loads(e[6:].strip())
        if payload.get("type") == "token":
            parts.append(str(payload.get("content") or ""))
    assert "".join(parts) == "Hola mundo"


def test_sse_token_format():
    line = sse_token("x")
    assert line.startswith("data: ")
    assert line.endswith("\n\n")


def test_sse_done_includes_elapsed_ms():
    line = sse_done(response="ok", extra={"elapsed_ms": 31760})
    payload = json.loads(line[6:].strip())
    assert payload["type"] == "done"
    assert payload["elapsed_ms"] == 31760


def test_emit_chat_reply_sse_done_elapsed_ms():
    async def _run() -> dict[str, object] | None:
        done_payload: dict[str, object] | None = None
        async for ev in emit_chat_reply_sse("Hola", delay_s=0, elapsed_ms=1500):
            if ev.startswith("data: {"):
                payload = json.loads(ev[6:].strip())
                if payload.get("type") == "done":
                    done_payload = payload
        return done_payload

    payload = asyncio.run(_run())
    assert payload is not None
    assert payload.get("elapsed_ms") == 1500
