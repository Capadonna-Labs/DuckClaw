"""
Google Trends MCP Bridge — stdio hacia google-trends-mcp (PyPI, pytrends).

Spec: specs/features/Google Trends MCP (Macro Interest Finanz).md
Requiere: pip/uv instalar google-trends-mcp (extra google-trends); el ejecutable
          google-trends-mcp en el PATH del venv del gateway (recomendado).
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Optional

_log = logging.getLogger(__name__)

_DEFAULT_TOOL_ALLOWLIST = frozenset({
    "interest_over_time",
    "related_queries",
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


def _default_stdio_command_and_args() -> tuple[str, list[str]]:
    """
    Resuelve cómo arrancar el servidor MCP: script del venv, which, o uvx.
    """
    bin_dir = Path(sys.executable).resolve().parent
    script = bin_dir / "google-trends-mcp"
    if script.is_file():
        return str(script), []
    wx = shutil.which("google-trends-mcp")
    if wx:
        return wx, []
    uvx = shutil.which("uvx")
    if uvx:
        return uvx, ["google-trends-mcp"]
    return "", []


def _resolve_stdio_params(cfg: dict) -> tuple[str, list[str]]:
    cmd = cfg.get("command")
    args = cfg.get("args")
    if isinstance(cmd, str) and cmd.strip():
        if isinstance(args, list):
            return cmd.strip(), [str(a) for a in args]
        return cmd.strip(), []
    return _default_stdio_command_and_args()


async def connect_google_trends_mcp(
    *,
    tool_allowlist: Optional[frozenset[str]] = None,
    manifest_config: Optional[dict] = None,
) -> list[Any]:
    """
    Levanta google-trends-mcp por stdio y devuelve StructuredTools (solo nombres en allowlist).
    """
    if not _mcp_available():
        return []

    cfg = manifest_config if isinstance(manifest_config, dict) else {}
    backend = str(cfg.get("backend") or "pytrends").strip().lower()
    if backend not in ("pytrends", ""):
        _log.warning("google_trends MCP: backend %s no soportado en esta entrega; omitido", backend)
        return []

    command, args = _resolve_stdio_params(cfg)
    if not command:
        _log.warning(
            "google_trends MCP: no se encontró google-trends-mcp ni uvx; "
            "instala el extra (uv sync --extra google-trends) y reinicia el gateway",
        )
        return []

    allow = tool_allowlist if tool_allowlist is not None else _DEFAULT_TOOL_ALLOWLIST

    try:
        from mcp.client.stdio import StdioServerParameters
    except ImportError:
        return []

    env = os.environ.copy()
    server_params = StdioServerParameters(
        command=command,
        args=args,
        env=env,
    )
    try:
        from duckclaw.forge.skills.mcp_stdio_util import mcp_stdio_list_tools

        tools_specs = await mcp_stdio_list_tools(server_params)
    except Exception as exc:
        _log.warning("google_trends MCP: fallo al iniciar proceso %s %s: %s", command, args, exc)
        return []
    result: list[Any] = []
    for t in tools_specs:
        name = getattr(t, "name", None) or str(t)
        if name not in allow:
            continue
        tool = _mcp_tool_to_structured(server_params, t, name)
        if tool:
            result.append(tool)

    if not result and tools_specs:
        _log.warning(
            "google_trends MCP: allowlist no coincidió con tools del servidor (%d listadas)",
            len(tools_specs),
        )
    return result


def _mcp_tool_to_structured(server_params: Any, tool_spec: Any, name: str) -> Optional[Any]:
    from duckclaw.forge.skills.mcp_stdio_util import mcp_stdio_call_tool
    from langchain_core.tools import StructuredTool

    def _sync_call(**kwargs: Any) -> str:
        return _run_async_from_sync(mcp_stdio_call_tool(server_params, name, dict(kwargs)))

    desc = getattr(tool_spec, "description", None) or f"Google Trends MCP: {name}"
    return StructuredTool.from_function(
        _sync_call,
        name=name,
        description=desc,
    )


def _allowlist_from_config(manifest_google_trends_config: Optional[dict]) -> frozenset[str]:
    if not manifest_google_trends_config or not isinstance(manifest_google_trends_config, dict):
        return _DEFAULT_TOOL_ALLOWLIST
    raw = manifest_google_trends_config.get("tool_allowlist")
    if not isinstance(raw, list) or not raw:
        return _DEFAULT_TOOL_ALLOWLIST
    names = {str(x).strip() for x in raw if str(x).strip()}
    return frozenset(names) if names else _DEFAULT_TOOL_ALLOWLIST


def register_google_trends_skill(
    tools_list: list[Any],
    manifest_google_trends_config: Optional[dict] = None,
) -> None:
    """Registra herramientas Google Trends MCP si el manifest define google_trends:."""
    if manifest_google_trends_config is None:
        return
    cfg = manifest_google_trends_config if isinstance(manifest_google_trends_config, dict) else {}
    allow = _allowlist_from_config(cfg)
    try:
        gt_tools = _run_async_from_sync(
            connect_google_trends_mcp(tool_allowlist=allow, manifest_config=cfg)
        )
        tools_list.extend(gt_tools)
    except Exception:
        _log.debug("register_google_trends_skill omitido", exc_info=True)
