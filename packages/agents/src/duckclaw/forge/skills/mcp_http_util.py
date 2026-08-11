"""Shared MCP Streamable HTTP client helpers."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, List, Optional, TypeVar

T = TypeVar("T")


def _format_mcp_content_part(part: Any) -> str:
    text = getattr(part, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    data = getattr(part, "data", None)
    if data is not None:
        import base64

        mime = (
            getattr(part, "mimeType", None)
            or getattr(part, "mime_type", None)
            or "image/png"
        )
        if isinstance(data, (bytes, bytearray)):
            b64 = base64.standard_b64encode(bytes(data)).decode("ascii")
        else:
            b64 = str(data)
        return f"type='image' mime='{mime}' data='{b64}'"
    return str(part)


def format_mcp_call_tool_result(result: Any) -> str:
    content = getattr(result, "content", None) or []
    if isinstance(content, list) and content:
        parts = [_format_mcp_content_part(part) for part in content]
        return "\n".join(p for p in parts if p)
    return str(result)


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
    from duckclaw.forge.skills.mcp_http_pool import mcp_http_list_tools_pooled, mcp_http_pool_enabled

    if mcp_http_pool_enabled():
        return mcp_http_list_tools_pooled(url, headers=headers)

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
    from duckclaw.forge.skills.mcp_http_pool import mcp_http_call_tool_pooled, mcp_http_pool_enabled

    if mcp_http_pool_enabled():
        return mcp_http_call_tool_pooled(url, name, arguments, headers=headers)

    async def _call(session: Any) -> str:
        try:
            result = await session.call_tool(name, arguments or {})
            return format_mcp_call_tool_result(result)
        except Exception as exc:
            return f"Error MCP ({name}): {exc}"

    return await mcp_http_with_session(url, headers=headers, work=_call)
