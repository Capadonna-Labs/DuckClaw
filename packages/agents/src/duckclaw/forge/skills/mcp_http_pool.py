"""
Pool de sesión MCP streamable HTTP (Android-MCP, etc.).

Cada ``mcp_http_call_tool`` efímero abre transport + initialize + terminate.
Este módulo reutiliza una sesión por endpoint (url + headers) ~120s entre llamadas.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import threading
import time
from typing import Any, Awaitable, Callable, List, Optional, TypeVar

_log = logging.getLogger(__name__)

_IDLE_TTL_S = float(os.environ.get("DUCKCLAW_MCP_HTTP_POOL_TTL_S", "120") or "120")
T = TypeVar("T")


def _session_key(url: str, headers: dict[str, str] | None) -> str:
    hdr = json.dumps(headers or {}, sort_keys=True, ensure_ascii=False)
    digest = hashlib.sha256(f"{url}|{hdr}".encode()).hexdigest()[:16]
    return f"{url}#{digest}"


def _format_mcp_content_part(part: Any) -> str:
    text = getattr(part, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    data = getattr(part, "data", None)
    if data is not None:
        mime = (
            getattr(part, "mimeType", None)
            or getattr(part, "mime_type", None)
            or "image/png"
        )
        if isinstance(data, (bytes, bytearray)):
            import base64

            b64 = base64.standard_b64encode(bytes(data)).decode("ascii")
        else:
            b64 = str(data)
        return f"type='image' mime='{mime}' data='{b64}'"
    return str(part)


def _format_call_tool_result(result: Any) -> str:
    content = getattr(result, "content", None) or []
    if isinstance(content, list) and content:
        parts = [_format_mcp_content_part(part) for part in content]
        return "\n".join(p for p in parts if p)
    return str(result)


class _Slot:
    """One live MCP session (per url + headers)."""

    def __init__(self) -> None:
        self.http_client: Any = None
        self.transport_cm: Any = None
        self.session_cm: Any = None
        self.session: Any = None
        self.last_used = 0.0


class _McpHttpPool:
    """One session per (url, headers) on a dedicated event-loop thread.

    It used to hold a single session: each connector evicted the previous one, so every turn
    reconnected all connectors, and two concurrent tool builds (a chat turn and the admin
    capabilities probe) closed each other's session mid ``list_tools`` (empty-message errors).
    """

    def __init__(self) -> None:
        self._thread_lock = threading.Lock()
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._slots: dict[str, _Slot] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _start_loop_thread(self) -> None:
        if self._loop is not None and self._thread is not None and self._thread.is_alive():
            return

        def _run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._loop = loop
            self._ready.set()
            loop.run_forever()

        self._ready.clear()
        self._thread = threading.Thread(target=_run, name="mcp-http-pool", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=30.0)
        if self._loop is None:
            raise RuntimeError("mcp HTTP pool: event loop thread failed to start")

    def _run_coro(self, coro: Awaitable[T], *, timeout: float = 120.0) -> T:
        with self._thread_lock:
            self._start_loop_thread()
            assert self._loop is not None
            fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=timeout)

    async def _close_slot_async(self, key: str) -> None:
        slot = self._slots.pop(key, None)
        if slot is None:
            return
        for cm in (slot.session_cm, slot.transport_cm):
            if cm is not None:
                try:
                    await cm.__aexit__(None, None, None)
                except Exception:
                    pass
        if slot.http_client is not None:
            try:
                await slot.http_client.aclose()
            except Exception:
                pass

    def _lock_for(self, key: str) -> asyncio.Lock:
        # Created and used only on the pool's loop thread.
        lock = self._locks.get(key)
        if lock is None:
            lock = self._locks[key] = asyncio.Lock()
        return lock

    def _fresh(self, key: str) -> Any:
        slot = self._slots.get(key)
        if slot is not None and slot.session is not None and (time.monotonic() - slot.last_used) < _IDLE_TTL_S:
            slot.last_used = time.monotonic()
            return slot.session
        return None

    async def _ensure_connected_async(self, url: str, headers: dict[str, str]) -> Any:
        import httpx
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        key = _session_key(url, headers)
        session = self._fresh(key)
        if session is not None:
            return session
        async with self._lock_for(key):
            session = self._fresh(key)
            if session is not None:
                return session
            await self._close_slot_async(key)
            t0 = time.perf_counter()
            slot = _Slot()
            slot.http_client = httpx.AsyncClient(headers=headers or {}, timeout=60.0)
            slot.transport_cm = streamable_http_client(url, http_client=slot.http_client)
            read_stream, write_stream, _get_session_id = await slot.transport_cm.__aenter__()
            del _get_session_id
            slot.session_cm = ClientSession(read_stream, write_stream)
            slot.session = await slot.session_cm.__aenter__()
            await slot.session.initialize()
            slot.last_used = time.monotonic()
            self._slots[key] = slot
            _log.info(
                "mcp HTTP pool: sesión lista en %.2fs url=%s",
                time.perf_counter() - t0,
                url,
            )
            return slot.session

    async def _list_tools_async(self, url: str, headers: dict[str, str]) -> List[Any]:
        session = await self._ensure_connected_async(url, headers)
        try:
            tools_result = await session.list_tools()
        except Exception:
            await self._close_slot_async(_session_key(url, headers))
            raise
        return list(getattr(tools_result, "tools", []) or [])

    async def _call_tool_async(
        self,
        url: str,
        headers: dict[str, str],
        name: str,
        arguments: Optional[dict[str, Any]],
    ) -> str:
        key = _session_key(url, headers)
        session = await self._ensure_connected_async(url, headers)
        t0 = time.perf_counter()
        try:
            result = await session.call_tool(name, arguments or {})
            out = _format_call_tool_result(result)
            _log.debug("mcp HTTP pool: tool=%s ok in %.2fs", name, time.perf_counter() - t0)
            return out
        except Exception as exc:
            _log.warning(
                "mcp HTTP pool: tool=%s failed in %.2fs: %r",
                name,
                time.perf_counter() - t0,
                exc,
            )
            await self._close_slot_async(key)
            return f"Error MCP ({name}): {exc!r}"

    def list_tools(self, url: str, *, headers: dict[str, str] | None = None) -> List[Any]:
        hdr = dict(headers or {})
        return self._run_coro(self._list_tools_async(url, hdr))

    def call_tool(
        self,
        url: str,
        name: str,
        arguments: Optional[dict[str, Any]] = None,
        *,
        headers: dict[str, str] | None = None,
    ) -> str:
        hdr = dict(headers or {})
        return self._run_coro(self._call_tool_async(url, hdr, name, arguments))


_POOL = _McpHttpPool()


def mcp_http_pool_enabled() -> bool:
    raw = (os.environ.get("DUCKCLAW_MCP_HTTP_POOL") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def mcp_http_list_tools_pooled(url: str, *, headers: dict[str, str] | None = None) -> List[Any]:
    return _POOL.list_tools(url, headers=headers)


def mcp_http_call_tool_pooled(
    url: str,
    name: str,
    arguments: Optional[dict[str, Any]] = None,
    *,
    headers: dict[str, str] | None = None,
) -> str:
    return _POOL.call_tool(url, name, arguments, headers=headers)
