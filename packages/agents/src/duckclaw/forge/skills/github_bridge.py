"""
GitHub MCP Bridge — conecta el agente con github-mcp-server vía stdio.

Spec: specs/Integracion_de_GitHub_MCP_en_DuckClaw.md
Requiere: pip install mcp  (o uv sync --extra github)
"""

from __future__ import annotations

import asyncio
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from duckclaw.forge.skills.mcp_tool_args_schema import mcp_input_schema_to_args_model

_DESTRUCTIVE_TOOLS = frozenset({
    "github_delete_branch",
    "github_merge_pr",
    "github_force_push",
    "delete_branch",
    "merge_pr",
    "force_push",
})


def _run_async_from_sync(coro) -> Any:
    """
    Ejecuta una coroutine desde contexto síncrono.
    Si ya hay un event loop corriendo (ej. Telegram, FastAPI), usa un thread
    separado para evitar 'RuntimeError: This event loop is already running'.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result()


def _mcp_available() -> bool:
    """True si el paquete mcp está instalado."""
    try:
        import mcp  # noqa: F401
        return True
    except ImportError:
        return False


async def connect_github_mcp(
    allowed_repos: Optional[list[str]] = None,
    token_env: str = "GITHUB_TOKEN",
    hitl_destructive: bool = True,
) -> list[Any]:
    """
    Levanta el github-mcp-server como proceso hijo y devuelve las herramientas
    MCP como StructuredTools de LangChain. Zero-Trust: token con scope limitado.

    Args:
        allowed_repos: Lista de repos permitidos (ej. ["owner/repo"]).
        token_env: Variable de entorno con el token.
        hitl_destructive: Si True, herramientas destructivas requieren /approve.

    Returns:
        Lista de StructuredTool. Vacía si mcp no está instalado o falta token.
    """
    if not _mcp_available():
        return []

    token = os.environ.get(token_env or "GITHUB_TOKEN", "").strip()
    if not token:
        return []

    try:
        from mcp.client.stdio import StdioServerParameters
    except ImportError:
        return []

    env = os.environ.copy()
    env["GITHUB_PERSONAL_ACCESS_TOKEN"] = token

    server_params = StdioServerParameters(
        command="npx",
        args=["-y", "@modelcontextprotocol/server-github"],
        env=env,
    )
    try:
        from duckclaw.forge.skills.mcp_stdio_util import mcp_stdio_list_tools

        tools_specs = await mcp_stdio_list_tools(server_params)
    except Exception:
        return []
    from langchain_core.tools import StructuredTool

    result: list[Any] = []
    for t in tools_specs:
        name = getattr(t, "name", None) or str(t)
        is_destructive = any(d in name.lower() for d in _DESTRUCTIVE_TOOLS)
        if is_destructive and hitl_destructive:
            tool = _wrap_with_hitl(t, name)
        else:
            tool = _mcp_tool_to_structured(server_params, t, name)
        if tool:
            result.append(tool)

    return result


def _mcp_tool_to_structured(server_params: Any, tool_spec: Any, name: str) -> Optional[Any]:
    """Convierte una tool MCP en StructuredTool de LangChain."""
    from duckclaw.forge.skills.mcp_stdio_util import mcp_stdio_call_tool
    from langchain_core.tools import StructuredTool

    raw_schema = getattr(tool_spec, "inputSchema", None) or getattr(tool_spec, "input_schema", None)
    args_model = mcp_input_schema_to_args_model(
        raw_schema if isinstance(raw_schema, dict) else None,
        f"{name}_github",
    )

    def _sync_call(**kwargs: Any) -> str:
        validated = args_model(**kwargs)
        payload = validated.model_dump(exclude_none=True)
        return _run_async_from_sync(mcp_stdio_call_tool(server_params, name, payload))

    desc = getattr(tool_spec, "description", None) or f"GitHub MCP tool: {name}"
    return StructuredTool.from_function(
        _sync_call,
        name=name,
        description=desc,
        args_schema=args_model,
        infer_schema=False,
    )


def _wrap_with_hitl(tool_spec: Any, name: str) -> Optional[Any]:
    """Envuelve una tool destructiva con guard HITL (requiere /approve)."""
    from langchain_core.tools import StructuredTool

    raw_schema = getattr(tool_spec, "inputSchema", None) or getattr(tool_spec, "input_schema", None)
    args_model = mcp_input_schema_to_args_model(
        raw_schema if isinstance(raw_schema, dict) else None,
        f"{name}_github_hitl",
    )

    def _call_hitl(**kwargs: Any) -> str:
        return (
            f"[HITL] La acción {name} requiere aprobación del usuario. "
            "Usa /approve en Telegram para confirmar, o /reject para cancelar."
        )

    desc = (getattr(tool_spec, "description", None) or f"GitHub MCP: {name}") + " [Requiere /approve]"
    return StructuredTool.from_function(
        _call_hitl,
        name=name,
        description=desc,
        args_schema=args_model,
        infer_schema=False,
    )


def register_github_skill(
    tools_list: list[Any],
    manifest_github_config: Optional[dict] = None,
) -> None:
    """
    Registra las herramientas de GitHub en la lista de tools.
    Llamar desde el Assembler cuando el manifest tiene skills.github.
    """
    if not manifest_github_config:
        return
    try:
        gh_tools = _run_async_from_sync(
            connect_github_mcp(
                allowed_repos=manifest_github_config.get("allowed_repos"),
                token_env=manifest_github_config.get("token_env", "GITHUB_TOKEN"),
                hitl_destructive=manifest_github_config.get("hitl_destructive", True),
            )
        )
        tools_list.extend(gh_tools)
    except Exception:
        pass
