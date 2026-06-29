"""Shared MCP Streamable HTTP client helpers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, List, Optional, TypeVar

T = TypeVar("T")


async def mcp_http_with_session(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    work: Callable[[Any], Awaitable[T]],
) -> T:
    import httpx
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with httpx.AsyncClient(headers=headers or {}, timeout=60.0) as http_client:
        async with streamable_http_client(url, http_client=http_client) as (
            read_stream,
            write_stream,
            _get_session_id,
        ):
            del _get_session_id
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                return await work(session)


async def mcp_http_list_tools(url: str, *, headers: dict[str, str] | None = None) -> List[Any]:
    async def _list(session: Any) -> List[Any]:
        tools_result = await session.list_tools()
        return list(getattr(tools_result, "tools", []) or [])

    return await mcp_http_with_session(url, headers=headers, work=_list)


async def mcp_http_call_tool(
    url: str,
    name: str,
    arguments: Optional[dict[str, Any]] = None,
    *,
    headers: dict[str, str] | None = None,
) -> str:
    async def _call(session: Any) -> str:
        try:
            result = await session.call_tool(name, arguments or {})
            content = getattr(result, "content", None) or []
            if isinstance(content, list) and content:
                part = content[0]
                return getattr(part, "text", str(part))
            return str(result)
        except Exception as exc:
            return f"Error MCP ({name}): {exc}"

    return await mcp_http_with_session(url, headers=headers, work=_call)
