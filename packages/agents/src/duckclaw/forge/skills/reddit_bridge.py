"""
Reddit MCP Bridge — stdio hacia mcp-reddit (npm).

Spec: specs/features/quant/QUANT_REDDIT_MCP_SENTIMENT.md
Requiere: pip mcp; Node/npx; REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, REDDIT_USER_AGENT,
          REDDIT_USERNAME, REDDIT_PASSWORD en el entorno del gateway.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import shutil
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

from duckclaw.forge.skills.mcp_tool_args_schema import mcp_input_schema_to_args_model

_log = logging.getLogger(__name__)

_REDDIT_ENV_KEYS = (
    "REDDIT_CLIENT_ID",
    "REDDIT_CLIENT_SECRET",
    "REDDIT_USER_AGENT",
    "REDDIT_USERNAME",
    "REDDIT_PASSWORD",
)

# Herramientas de solo lectura cuando read_only=true.
# mcp-reddit 1.0.x usaba nombres cortos; 1.1.x+ usa prefijo `reddit_` (list_tools devuelve p.ej. reddit_get_post).
_READ_ONLY_TOOL_NAMES = frozenset({
    "search_reddit",
    "get_subreddit_posts",
    "get_subreddit_info",
    "get_post",
    "get_post_comments",
    "get_user_info",
    "get_user_posts",
    "get_user_comments",
    "reddit_search_reddit",
    "reddit_search_subreddits",
    "reddit_get_subreddit_posts",
    "reddit_get_subreddit_info",
    "reddit_get_subreddit_rules",
    "reddit_get_post",
    "reddit_get_post_comments",
    "reddit_get_user_info",
    "reddit_get_user_posts",
    "reddit_get_user_comments",
    "reddit_get_user_overview",
    "reddit_get_front_page_posts",
    "reddit_get_popular_subreddits",
    "reddit_get_new_subreddits",
})

# Mutadoras: HITL si read_only=false y hitl_destructive.
_MUTATING_TOOL_NAMES = frozenset({
    "submit_post",
    "submit_comment",
    "edit_post_or_comment",
    "delete_post_or_comment",
    "upload_image",
    "reddit_submit_post",
    "reddit_submit_comment",
    "reddit_edit_post_or_comment",
    "reddit_delete_post_or_comment",
    "reddit_upload_image",
    "reddit_vote",
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


def _reddit_mcp_cache_dir() -> Path:
    custom = (os.environ.get("DUCKCLAW_REDDIT_MCP_CACHE_DIR") or "").strip()
    if custom:
        return Path(custom).resolve()
    from duckclaw.forge.skills.telegram_mcp_bridge import infer_repo_root

    return infer_repo_root() / ".mcp-cache" / "reddit"


def reddit_mcp_prefetch_server_path(npm_package: str = "mcp-reddit") -> Optional[Path]:
    """Ruta a dist/server.js si existe prefetch en .mcp-cache/reddit."""
    pkg = (npm_package or "mcp-reddit").strip() or "mcp-reddit"
    server = _reddit_mcp_cache_dir() / "node_modules" / pkg / "dist" / "server.js"
    return server if server.is_file() else None


def reddit_mcp_using_prefetch(npm_package: str = "mcp-reddit") -> bool:
    return reddit_mcp_prefetch_server_path(npm_package) is not None


def reddit_mcp_server_params(npm_package: str = "mcp-reddit") -> Any:
    """
    Stdio hacia mcp-reddit sin npx cuando hay prefetch o binario global.

    Prioridad: DUCKCLAW_REDDIT_MCP_COMMAND → node + .mcp-cache → which(mcp-reddit) → npx.
    """
    from mcp.client.stdio import StdioServerParameters

    env = os.environ.copy()
    custom_cmd = (os.environ.get("DUCKCLAW_REDDIT_MCP_COMMAND") or "").strip()
    if custom_cmd:
        args_raw = (os.environ.get("DUCKCLAW_REDDIT_MCP_ARGS") or "").strip()
        args = shlex.split(args_raw) if args_raw else []
        return StdioServerParameters(command=custom_cmd, args=args, env=env)

    cached = reddit_mcp_prefetch_server_path(npm_package)
    if cached is not None:
        node = (os.environ.get("DUCKCLAW_REDDIT_MCP_NODE") or shutil.which("node") or "node").strip()
        return StdioServerParameters(command=node, args=[str(cached)], env=env)

    global_bin = shutil.which("mcp-reddit")
    if global_bin:
        return StdioServerParameters(command=global_bin, args=[], env=env)

    pkg = (npm_package or "mcp-reddit").strip() or "mcp-reddit"
    return StdioServerParameters(
        command="npx",
        args=["--quiet", "-y", pkg],
        env=env,
    )


def warm_reddit_mcp_pool(*, npm_package: str = "mcp-reddit") -> None:
    """
    Pre-calienta el pool MCP de Reddit (npx cold start). Seguro en hilo de fondo del gateway.
    """
    if not _mcp_available() or not _reddit_env_ready():
        return
    try:
        from duckclaw.forge.skills.reddit_mcp_pool import reddit_mcp_list_tools

        server_params = reddit_mcp_server_params(npm_package)
        warm_timeout = float(
            os.environ.get("DUCKCLAW_REDDIT_MCP_WARM_TIMEOUT_S", "90") or "90"
        )
        t0 = time.perf_counter()
        tools_specs = reddit_mcp_list_tools(server_params, timeout=warm_timeout)
        _log.info(
            "reddit MCP warm: list_tools (%d) en %.2fs",
            len(tools_specs),
            time.perf_counter() - t0,
        )
    except Exception as exc:
        _log.warning("reddit MCP warm: %s", exc)


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

    server_params = reddit_mcp_server_params(npm_package)
    t_connect = time.perf_counter()
    try:
        from duckclaw.forge.skills.reddit_mcp_pool import (
            reddit_mcp_list_tools,
            reddit_mcp_pool_session_ready,
        )

        if reddit_mcp_pool_session_ready(server_params):
            list_timeout = float(
                os.environ.get("DUCKCLAW_REDDIT_MCP_LIST_TOOLS_TIMEOUT_S", "60") or "60"
            )
        elif reddit_mcp_using_prefetch(npm_package):
            list_timeout = float(
                os.environ.get("DUCKCLAW_REDDIT_MCP_REGISTER_TIMEOUT_S", "45") or "45"
            )
        else:
            list_timeout = float(
                os.environ.get("DUCKCLAW_REDDIT_MCP_REGISTER_TIMEOUT_S", "12") or "12"
            )
        tools_specs = await asyncio.to_thread(
            reddit_mcp_list_tools, server_params, timeout=list_timeout
        )
        elapsed = time.perf_counter() - t_connect
        _log.info(
            "reddit MCP: list_tools (%d) en %.2fs (pool reutilizable)",
            len(tools_specs),
            elapsed,
        )
    except Exception as exc:
        elapsed = time.perf_counter() - t_connect
        cmd = getattr(server_params, "command", None) or "?"
        _log.warning("reddit MCP: no se pudo iniciar %s: %s", cmd, exc)
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
    from duckclaw.forge.skills.reddit_mcp_pool import reddit_mcp_call_tool
    from langchain_core.tools import StructuredTool

    raw_schema = getattr(tool_spec, "inputSchema", None) or getattr(tool_spec, "input_schema", None)
    args_model = mcp_input_schema_to_args_model(
        raw_schema if isinstance(raw_schema, dict) else None,
        f"{name}_reddit",
    )

    def _sync_call(**kwargs: Any) -> str:
        validated = args_model(**kwargs)
        payload = validated.model_dump(exclude_none=True)
        return reddit_mcp_call_tool(server_params, name, payload)

    desc = getattr(tool_spec, "description", None) or f"Reddit MCP: {name}"
    return StructuredTool.from_function(
        _sync_call,
        name=name,
        description=desc,
        args_schema=args_model,
        infer_schema=False,
    )


def _wrap_with_hitl(tool_spec: Any, name: str) -> Optional[Any]:
    from langchain_core.tools import StructuredTool

    raw_schema = getattr(tool_spec, "inputSchema", None) or getattr(tool_spec, "input_schema", None)
    args_model = mcp_input_schema_to_args_model(
        raw_schema if isinstance(raw_schema, dict) else None,
        f"{name}_reddit_hitl",
    )

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
        args_schema=args_model,
        infer_schema=False,
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
        if rd_tools:
            names = [getattr(t, "name", "") or "" for t in rd_tools]
            _log.info(
                "reddit MCP: registered %d tools: %s",
                len(rd_tools),
                ", ".join(sorted(n for n in names if n)),
            )
    except Exception:
        _log.warning("register_reddit_skill falló", exc_info=True)
