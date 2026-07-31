"""
YouTube Transcript MCP Bridge — stdio vía uvx (jkawamoto/mcp-youtube-transcript).

Read-only: transcripciones y metadata de videos YouTube. Sin credenciales obligatorias.
Workers opt-in vía manifest skill `youtube_transcript:`.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import shutil
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from duckclaw.forge.skills.mcp_tool_args_schema import mcp_input_schema_to_args_model

_log = logging.getLogger(__name__)

_GIT_REPO = "git+https://github.com/jkawamoto/mcp-youtube-transcript"
_DEFAULT_RESPONSE_LIMIT = 15000
# ponytail: uvx may resolve mcp 2.x; FastMCP removed from mcp.server — pin 1.x for this MCP
_MCP_UVX_PIN = "mcp>=1.9,<2"

_READ_ONLY_TOOL_NAMES = frozenset({
    "get_transcript",
    "get_timed_transcript",
    "get_video_info",
    "get_available_languages",
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


def _uvx_available() -> bool:
    return shutil.which("uvx") is not None


def _response_limit_from_config(cfg: dict[str, Any]) -> int:
    raw = cfg.get("response_limit", _DEFAULT_RESPONSE_LIMIT)
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        limit = _DEFAULT_RESPONSE_LIMIT
    return max(1000, min(limit, 50000))


def _allowed_tool_names(cfg: dict[str, Any]) -> frozenset[str]:
    """Manifest ``tools: [get_transcript, ...]`` narrows exposed MCP tools (opt-in whitelist)."""
    raw = cfg.get("tools")
    if not isinstance(raw, list) or not raw:
        return _READ_ONLY_TOOL_NAMES
    names = {str(item).strip() for item in raw if str(item).strip()}
    allowed = names & _READ_ONLY_TOOL_NAMES
    return allowed if allowed else _READ_ONLY_TOOL_NAMES


def _proxy_env_from_config(cfg: dict[str, Any], env: dict[str, str]) -> None:
    """Manifest/env proxy keys for youtube-transcript-api (egress IP blocks)."""
    for key in ("https_proxy", "http_proxy"):
        val = str(cfg.get(key) or env.get(key.upper()) or env.get(key) or "").strip()
        if val:
            env["HTTPS_PROXY" if key == "https_proxy" else "HTTP_PROXY"] = val
    for cfg_key, env_key in (
        ("webshare_proxy_username", "WEBSHARE_PROXY_USERNAME"),
        ("webshare_proxy_password", "WEBSHARE_PROXY_PASSWORD"),
    ):
        val = str(cfg.get(cfg_key) or env.get(env_key) or "").strip()
        if val:
            env[env_key] = val


def _proxy_cli_args_from_config(cfg: dict[str, Any]) -> list[str]:
    args: list[str] = []
    https = str(cfg.get("https_proxy") or "").strip()
    http = str(cfg.get("http_proxy") or "").strip()
    if https:
        args.extend(["--https-proxy", https])
    if http:
        args.extend(["--http-proxy", http])
    return args


def _normalize_youtube_tool_result(raw: str) -> str:
    """ponytail: steer LLM away from useless fallback cascade on YouTube IP blocks."""
    text = str(raw or "")
    lower = text.lower()
    if "429" in text or "too many requests" in lower or "google.com/sorry" in lower:
        return (
            "YOUTUBE_RATE_LIMIT: YouTube temporarily blocked this egress IP (429). "
            "Do not retry get_transcript or substitute web_search/tavily/run_browser_sandbox "
            "for the same video in this turn. Report cooldown (~30-60 min) or ask for a manual transcript."
        )
    if "sign in to confirm you're not a bot" in lower or "confirm you're not a bot" in lower:
        return (
            "YOUTUBE_BOT_BLOCK: YouTube requires session cookies from this cloud egress IP. "
            "Do not retry other YouTube tools this turn. Ask the user for a manual transcript."
        )
    return text


def youtube_transcript_mcp_server_params(
    manifest_config: Optional[dict[str, Any]] = None,
) -> Any:
    """Stdio hacia mcp-youtube-transcript (uvx)."""
    from mcp.client.stdio import StdioServerParameters

    cfg = manifest_config if isinstance(manifest_config, dict) else {}
    limit = _response_limit_from_config(cfg)
    env = os.environ.copy()
    _proxy_env_from_config(cfg, env)

    custom_cmd = (os.environ.get("DUCKCLAW_YOUTUBE_TRANSCRIPT_MCP_COMMAND") or "").strip()
    if custom_cmd:
        args_raw = (os.environ.get("DUCKCLAW_YOUTUBE_TRANSCRIPT_MCP_ARGS") or "").strip()
        args = shlex.split(args_raw) if args_raw else []
        return StdioServerParameters(command=custom_cmd, args=args, env=env)

    args = [
        "--from",
        _GIT_REPO,
        "--with",
        _MCP_UVX_PIN,
        "mcp-youtube-transcript",
        "--response-limit",
        str(limit),
    ]
    args.extend(_proxy_cli_args_from_config(cfg))
    return StdioServerParameters(
        command="uvx",
        args=args,
        env=env,
    )


async def connect_youtube_transcript_mcp(
    *,
    manifest_config: Optional[dict[str, Any]] = None,
) -> list[Any]:
    """Levanta MCP YouTube transcript y devuelve StructuredTools LangChain."""
    if not _mcp_available():
        _log.warning("youtube_transcript MCP: paquete mcp no instalado")
        return []
    if not _uvx_available():
        _log.warning(
            "youtube_transcript MCP: uvx no encontrado; instala uv "
            "(curl -LsSf https://astral.sh/uv/install.sh | sh)"
        )
        return []

    server_params = youtube_transcript_mcp_server_params(manifest_config)
    try:
        from duckclaw.forge.skills.mcp_stdio_util import mcp_stdio_list_tools

        tools_specs = await mcp_stdio_list_tools(server_params)
        _log.info("youtube_transcript MCP: list_tools (%d)", len(tools_specs))
    except Exception as exc:
        cmd = getattr(server_params, "command", None) or "?"
        _log.warning("youtube_transcript MCP: no se pudo iniciar %s: %s", cmd, exc)
        return []

    from langchain_core.tools import StructuredTool

    cfg = manifest_config if isinstance(manifest_config, dict) else {}
    allow = _allowed_tool_names(cfg)
    result: list[Any] = []
    for spec in tools_specs:
        name = getattr(spec, "name", None) or str(spec)
        if name not in allow:
            continue
        tool = _mcp_tool_to_structured(server_params, spec, name)
        if tool:
            result.append(tool)

    if not result and tools_specs:
        _log.warning(
            "youtube_transcript MCP: ninguna tool en allowlist (servidor listó %d)",
            len(tools_specs),
        )
    return result


def _mcp_tool_to_structured(server_params: Any, tool_spec: Any, name: str) -> Optional[Any]:
    from duckclaw.forge.skills.mcp_stdio_util import mcp_stdio_call_tool
    from langchain_core.tools import StructuredTool

    raw_schema = getattr(tool_spec, "inputSchema", None) or getattr(tool_spec, "input_schema", None)
    args_model = mcp_input_schema_to_args_model(
        raw_schema if isinstance(raw_schema, dict) else None,
        f"{name}_youtube_transcript",
    )

    def _sync_call(**kwargs: Any) -> str:
        validated = args_model(**kwargs)
        payload = validated.model_dump(exclude_none=True)
        raw = _run_async_from_sync(mcp_stdio_call_tool(server_params, name, payload))
        return _normalize_youtube_tool_result(raw)

    desc = getattr(tool_spec, "description", None) or f"YouTube transcript MCP: {name}"
    return StructuredTool.from_function(
        _sync_call,
        name=name,
        description=desc,
        args_schema=args_model,
        infer_schema=False,
    )


def register_youtube_transcript_skill(
    tools_list: list[Any],
    manifest_config: Optional[dict] = None,
) -> None:
    """Registra herramientas YouTube transcript MCP si el manifest define `youtube_transcript:`."""
    if not manifest_config:
        return
    cfg = manifest_config if isinstance(manifest_config, dict) else {}
    try:
        yt_tools = _run_async_from_sync(connect_youtube_transcript_mcp(manifest_config=cfg))
        tools_list.extend(yt_tools)
        if yt_tools:
            names = [getattr(t, "name", "") or "" for t in yt_tools]
            _log.info(
                "youtube_transcript MCP: registered %d tools: %s",
                len(yt_tools),
                ", ".join(sorted(n for n in names if n)),
            )
    except Exception:
        _log.warning("register_youtube_transcript_skill falló", exc_info=True)
