"""
Utilidades compartidas para clientes MCP por stdio (paquete `mcp` ≥ 1.x).

`stdio_client` es un async context manager; no es awaitable. Cada llamada a
herramienta abre y cierra un proceso hijo (npx / binario), coherente con el
ciclo de vida del transporte.
"""

from __future__ import annotations

from typing import Any, Awaitable, Callable, List, Optional, TypeVar

T = TypeVar("T")


async def mcp_stdio_with_session(
    server_params: Any,
    work: Callable[[Any], Awaitable[T]],
) -> T:
    """
    Ejecuta `work(session)` con stdio + ClientSession inicializados.
    `server_params` debe ser mcp.client.stdio.StdioServerParameters.
    """
    from mcp import ClientSession
    from mcp.client.stdio import stdio_client

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            return await work(session)


async def mcp_stdio_list_tools(server_params: Any) -> List[Any]:
    """Lista herramientas del servidor (una conexión efímera)."""

    async def _list(session: Any) -> List[Any]:
        tools_result = await session.list_tools()
        return list(getattr(tools_result, "tools", []) or [])

    return await mcp_stdio_with_session(server_params, _list)


async def mcp_stdio_call_tool(
    server_params: Any,
    name: str,
    arguments: Optional[dict[str, Any]] = None,
) -> str:
    """Invoca tools/call y devuelve texto agregado del resultado."""

    async def _call(session: Any) -> str:
        try:
            result = await session.call_tool(name, arguments or {})
            content = getattr(result, "content", None) or []
            if isinstance(content, list) and content:
                part = content[0]
                return getattr(part, "text", str(part))
            return str(result)
        except Exception as e:
            return f"Error MCP ({name}): {e}"

    return await mcp_stdio_with_session(server_params, _call)
