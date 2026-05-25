"""
Pool de sesión MCP stdio para mcp-reddit.

Cada ``mcp_stdio_call_tool`` efímero lanza ``npx -y mcp-reddit`` (10–60s en cold start).
Este módulo mantiene un proceso hijo vivo ~120s entre llamadas del mismo gateway.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from typing import Any, Optional

_log = logging.getLogger(__name__)

_IDLE_TTL_S = float(
    __import__("os").environ.get("DUCKCLAW_REDDIT_MCP_POOL_TTL_S", "120") or "120"
)


def _params_key(server_params: Any) -> tuple[str, tuple[str, ...]]:
    cmd = str(getattr(server_params, "command", "") or "")
    args = tuple(getattr(server_params, "args", None) or ())
    return cmd, args


class _RedditMcpPool:
    def __init__(self) -> None:
        self._thread_lock = threading.Lock()
        self._connect_lock: Optional[asyncio.Lock] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._params_key: tuple[str, tuple[str, ...]] | None = None
        self._session: Any = None
        self._stdio_cm: Any = None
        self._session_cm: Any = None
        self._last_used = 0.0

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
        self._thread = threading.Thread(target=_run, name="reddit-mcp-pool", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=30.0)
        if self._loop is None:
            raise RuntimeError("reddit MCP pool: event loop thread failed to start")

    def _run_coro(self, coro: Any, *, timeout: float = 120.0) -> Any:
        with self._thread_lock:
            self._start_loop_thread()
            assert self._loop is not None
            fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return fut.result(timeout=timeout)

    async def _disconnect_async(self) -> None:
        if self._session_cm is not None:
            try:
                await self._session_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._session_cm = None
            self._session = None
        if self._stdio_cm is not None:
            try:
                await self._stdio_cm.__aexit__(None, None, None)
            except Exception:
                pass
            self._stdio_cm = None
        self._params_key = None

    def _connect_lock_for_loop(self) -> asyncio.Lock:
        if self._connect_lock is None:
            self._connect_lock = asyncio.Lock()
        return self._connect_lock

    async def _ensure_connected_async(self, server_params: Any) -> Any:
        from mcp import ClientSession
        from mcp.client.stdio import stdio_client

        key = _params_key(server_params)
        now = time.monotonic()
        if (
            self._session is not None
            and self._params_key == key
            and (now - self._last_used) < _IDLE_TTL_S
        ):
            self._last_used = now
            return self._session

        async with self._connect_lock_for_loop():
            now = time.monotonic()
            if (
                self._session is not None
                and self._params_key == key
                and (now - self._last_used) < _IDLE_TTL_S
            ):
                self._last_used = now
                return self._session

            await self._disconnect_async()
            t0 = time.perf_counter()
            self._stdio_cm = stdio_client(server_params)
            read_stream, write_stream = await self._stdio_cm.__aenter__()
            self._session_cm = ClientSession(read_stream, write_stream)
            self._session = await self._session_cm.__aenter__()
            await self._session.initialize()
            self._params_key = key
            self._last_used = time.monotonic()
            _log.info(
                "reddit MCP pool: sesión stdio lista en %.2fs (cmd=%s)",
                time.perf_counter() - t0,
                key[0],
            )
            return self._session

    async def _list_tools_async(self, server_params: Any) -> list[Any]:
        session = await self._ensure_connected_async(server_params)
        tools_result = await session.list_tools()
        self._last_used = time.monotonic()
        return list(getattr(tools_result, "tools", []) or [])

    async def _call_tool_async(
        self,
        server_params: Any,
        name: str,
        arguments: Optional[dict[str, Any]],
    ) -> str:
        session = await self._ensure_connected_async(server_params)
        t0 = time.perf_counter()
        try:
            result = await session.call_tool(name, arguments or {})
            content = getattr(result, "content", None) or []
            if isinstance(content, list) and content:
                part = content[0]
                out = getattr(part, "text", str(part))
            else:
                out = str(result)
            _log.info(
                "reddit MCP pool: tool=%s ok in %.2fs (reuse=%s)",
                name,
                time.perf_counter() - t0,
                self._params_key == _params_key(server_params),
            )
            return out
        except Exception as exc:
            _log.warning(
                "reddit MCP pool: tool=%s failed in %.2fs: %s",
                name,
                time.perf_counter() - t0,
                exc,
            )
            await self._disconnect_async()
            return f"Error MCP ({name}): {exc}"
        finally:
            self._last_used = time.monotonic()

    def list_tools(self, server_params: Any, *, timeout: float | None = None) -> list[Any]:
        effective = timeout
        if effective is None:
            effective = float(
                os.environ.get("DUCKCLAW_REDDIT_MCP_LIST_TOOLS_TIMEOUT_S", "180") or "180"
            )
        return self._run_coro(self._list_tools_async(server_params), timeout=effective)

    def session_ready(self, server_params: Any) -> bool:
        key = _params_key(server_params)
        with self._thread_lock:
            if self._session is None or self._params_key != key:
                return False
            return (time.monotonic() - self._last_used) < _IDLE_TTL_S

    def call_tool(
        self,
        server_params: Any,
        name: str,
        arguments: Optional[dict[str, Any]] = None,
    ) -> str:
        return self._run_coro(self._call_tool_async(server_params, name, arguments))


_POOL = _RedditMcpPool()


def reddit_mcp_list_tools(server_params: Any, *, timeout: float | None = None) -> list[Any]:
    return _POOL.list_tools(server_params, timeout=timeout)


def reddit_mcp_pool_session_ready(server_params: Any) -> bool:
    return _POOL.session_ready(server_params)


def reddit_mcp_call_tool(
    server_params: Any,
    name: str,
    arguments: Optional[dict[str, Any]] = None,
) -> str:
    return _POOL.call_tool(server_params, name, arguments)
