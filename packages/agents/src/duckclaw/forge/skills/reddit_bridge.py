"""
Reddit MCP Bridge — stdio hacia mcp-reddit (npm).

Spec: specs/features/Reddit MCP Social Sentiment (QuantClaw).md
Requiere: pip mcp; Node/npx; REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT,
          REDDIT_USERNAME, REDDIT_PASSWORD en el entorno del gateway.
"""

from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

_log = logging.getLogger(__name__)

_REDDIT_ENV_KEYS = (
    "REDDIT_CLIENT_ID",
    "REDDIT_CLIENT_SECRET",
    "REDDIT_USER_AGENT",
    "REDDIT_USERNAME",
    "REDDIT_PASSWORD",
)

# Herramientas de solo lectura permitidas cuando read_only=true (mcp-reddit).
_READ_ONLY_TOOL_NAMES = frozenset({
    "search_reddit",
    "get_subreddit_posts",
    "get_subreddit_info",
    "get_post",
    "get_post_comments",
    "get_user_info",
    "get_user_posts",
    "get_user_comments",
})

# Mutadoras conocidas en mcp-reddit: HITL si read_only=false y hitl_destructive.
_MUTATING_TOOL_NAMES = frozenset({
    "submit_post",
    "submit_comment",
    "edit_post_or_comment",
    "delete_post_or_comment",
    "upload_image",
})


def _run_async_from_sync(coro) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(asyncio.run, coro)
        return future.result()


def _mcp_available() -> bool:
    try:
        import mcp  # noqa: F401
        return True
    except ImportError:
        return False


def _reddit_env_ready() -> bool:
    return all(os.environ.get(k, "").strip() for k in _REDDIT_ENV_KEYS)


async def connect_reddit_mcp(
    *,
    read_only: bool = True,
    npm_package: str = "mcp-reddit",
    hitl_destructive: bool = True,
) -> list[Any]:
    """
    Levanta mcp-reddit con npx --quiet y devuelve StructuredTools LangChain.
    """
    if not _mcp_available():
        return []
    if not _reddit_env_ready():
        _log.warning(
            "reddit MCP: faltan variables de entorno Reddit (%s); no se registran tools",
            ", ".join(_REDDIT_ENV_KEYS),
        )
        return []

    try:
        from mcp.client.stdio import StdioServerParameters
    except ImportError:
        return []

    pkg = (npm_package or "mcp-reddit").strip() or "mcp-reddit"
    env = os.environ.copy()

    server_params = StdioServerParameters(
        command="npx",
        args=["--quiet", "-y", pkg],
        env=env,
    )
    try:
        from duckclaw.forge.skills.mcp_stdio_util import mcp_stdio_list_tools

        tools_specs = await mcp_stdio_list_tools(server_params)
    except Exception as exc:
        _log.warning("reddit MCP: no se pudo iniciar npx %s: %s", pkg, exc)
        return []
    from langchain_core.tools import StructuredTool

    result: list[Any] = []
    for t in tools_specs:
        name = getattr(t, "name", None) or str(t)
        if read_only:
            if name not in _READ_ONLY_TOOL_NAMES:
                continue
            tool = _mcp_tool_to_structured(server_params, t, name)
        else:
            is_mutating = name in _MUTATING_TOOL_NAMES
            if is_mutating and hitl_destructive:
                tool = _wrap_with_hitl(t, name)
            else:
                tool = _mcp_tool_to_structured(server_params, t, name)
        if tool:
            result.append(tool)

    if not result and tools_specs:
        _log.warning(
            "reddit MCP: ninguna tool registrada (read_only=%s; servidor listó %d tools)",
            read_only,
            len(tools_specs),
        )
    return result


def _mcp_tool_to_structured(server_params: Any, tool_spec: Any, name: str) -> Optional[Any]:
    from duckclaw.forge.skills.mcp_stdio_util import mcp_stdio_call_tool
    from langchain_core.tools import StructuredTool

    def _sync_call(**kwargs: Any) -> str:
        return _run_async_from_sync(mcp_stdio_call_tool(server_params, name, dict(kwargs)))

    desc = getattr(tool_spec, "description", None) or f"Reddit MCP: {name}"
    return StructuredTool.from_function(
        _sync_call,
        name=name,
        description=desc,
    )


def _wrap_with_hitl(tool_spec: Any, name: str) -> Optional[Any]:
    from langchain_core.tools import StructuredTool

    def _call_hitl(**kwargs: Any) -> str:
        return (
            f"[HITL] La acción Reddit {name} requiere aprobación del usuario. "
            "Usa /approve en Telegram para confirmar, o /reject para cancelar."
        )

    desc = (getattr(tool_spec, "description", None) or f"Reddit MCP: {name}") + " [Requiere /approve]"
    return StructuredTool.from_function(
        _call_hitl,
        name=name,
        description=desc,
    )


def register_reddit_skill(
    tools_list: list[Any],
    manifest_reddit_config: Optional[dict] = None,
) -> None:
    """Registra herramientas Reddit MCP si el manifest define `reddit:`."""
    if not manifest_reddit_config:
        return
    cfg = manifest_reddit_config if isinstance(manifest_reddit_config, dict) else {}
    try:
        rd_tools = _run_async_from_sync(
            connect_reddit_mcp(
                read_only=bool(cfg.get("read_only", True)),
                npm_package=str(cfg.get("npm_package") or "mcp-reddit"),
                hitl_destructive=bool(cfg.get("hitl_destructive", True)),
            )
        )
        tools_list.extend(rd_tools)
    except Exception:
        _log.debug("register_reddit_skill omitido", exc_info=True)
