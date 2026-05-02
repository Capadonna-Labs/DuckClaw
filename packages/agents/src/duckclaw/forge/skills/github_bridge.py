"""
GitHub MCP Bridge — proceso hijo oficial github-mcp-server (Docker stdio).

Spec: specs/core/03_Skills_and_Tooling_Framework.md, specs/features/GitClaw Worker.md
Requiere: pip install mcp (stdio cliente), Docker local con imagen pullada.

Verificar imagen (operadores): docker pull ghcr.io/github/github-mcp-server
"""

from __future__ import annotations

import asyncio
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from duckclaw.forge.skills.mcp_tool_args_schema import mcp_input_schema_to_args_model

_log = logging.getLogger(__name__)

# Imagen MCP oficial GitHub (override sólo si se sabe lo que se hace).
_GITHUB_IMAGE_DEFAULT = "ghcr.io/github/github-mcp-server"
# Toolsets explícitos: no incluir "projects". Orden irrelevante para el servidor.
_TOOLSETS_DEFAULT = "repos,issues,pull_requests,actions,code_security"

"""
Herramientas típicas expuestas (nombres exactos pueden variar por versión del servidor MCP):

  Lectura (todos los workers con MCP; sin --read-only efectivo sólo cuando el servidor
  permite writes y el proceso no lleva GITHUB_READ_ONLY):

  - get_file_contents (owner, repo, path, ref/branch opcional)
  - list_commits / commits similares
  - list_branches
  - list_releases / releases
  - search_code / búsqueda de código
  - list_workflow_runs, get_workflow_run / CI Actions
  - list_issues, get_issue
  - list_pull_requests, get_pull_request, get_pull_request_diff / PRs

  Escritura (sólo workers con MCP read-write, sin GITHUB_READ_ONLY):

  - create_issue, update_issue / mutación issues
  - create_pull_request / PRs
  - create_or_update_file / blobs y commits API

Repo por defecto sugerido en prompts si el worker no especifica: owner Capadonna-Labs,
repo duckclaw (los tools siguen exigiendo owner/repo salvo configuración MCP alternativa).

Documentación servidor: https://github.com/github/github-mcp-server
"""

_DESTRUCTIVE_TOOLS = frozenset({
    "github_delete_branch",
    "github_merge_pr",
    "github_force_push",
    "delete_branch",
    "merge_pr",
    "force_push",
})


def github_mcp_toolsets_default() -> str:
    """Toolsets MCP por defecto en DuckClaw (sin ``projects``)."""
    raw = (os.environ.get("GITHUB_TOOLSETS") or "").strip()
    return raw or _TOOLSETS_DEFAULT


def github_mcp_image_ref() -> str:
    """Imagen Docker del servidor MCP (env ``DUCKCLAW_GITHUB_MCP_IMAGE`` opcional)."""
    ref = (os.environ.get("DUCKCLAW_GITHUB_MCP_IMAGE") or _GITHUB_IMAGE_DEFAULT).strip()
    return ref or _GITHUB_IMAGE_DEFAULT


def github_docker_run_argv(*, read_only: bool) -> list[str]:
    """
    Args del binario ``docker`` para ``run`` (sans ``command='docker'``).

    Credenciales: ``-e VAR`` sin ``=valor`` propagan desde el env del proceso
    hijo de stdio que lanza MCP (inyectamos token/toolsets/read_only sólo ahí).
    """
    argv = [
        "run",
        "-i",
        "--rm",
        "--pull=missing",
        "-e",
        "GITHUB_PERSONAL_ACCESS_TOKEN",
        "-e",
        "GITHUB_TOOLSETS",
    ]
    if read_only:
        argv.extend(["-e", "GITHUB_READ_ONLY"])
    argv.append(github_mcp_image_ref())
    return argv


def github_mcp_merged_child_env(token: str, *, read_only: bool, toolsets: Optional[str] = None) -> dict[str, str]:
    """
    Copia superficial de ``os.environ`` + variables esperadas por el contenedor.
    ``token`` nunca debe loguearse.
    """
    base = dict(os.environ)
    if not read_only:
        base.pop("GITHUB_READ_ONLY", None)
    ts = (toolsets or "").strip() or github_mcp_toolsets_default()
    base["GITHUB_PERSONAL_ACCESS_TOKEN"] = token
    base["GITHUB_TOOLSETS"] = ts
    if read_only:
        base["GITHUB_READ_ONLY"] = "1"
    else:
        base.pop("GITHUB_READ_ONLY", None)
    return base


def compose_github_stdio_server_params(
    token: str,
    *,
    read_only: bool,
    toolsets: Optional[str] = None,
) -> Any:
    """Construye ``StdioServerParameters`` Docker + env (tests / utilidad operadores)."""
    from mcp.client.stdio import StdioServerParameters

    return StdioServerParameters(
        command="docker",
        args=github_docker_run_argv(read_only=read_only),
        env=github_mcp_merged_child_env(token, read_only=read_only, toolsets=toolsets),
    )


def _run_async_from_sync(coro) -> Any:
    """Ejecuta coroutine desde contexto síncrono (ThreadPoolExecutor si hay loop activo)."""
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


async def connect_github_mcp(
    allowed_repos: Optional[list[str]] = None,
    token_env: str = "GITHUB_TOKEN",
    hitl_destructive: bool = True,
    read_only: bool = False,
    toolsets_override: Optional[str] = None,
) -> list[Any]:
    """
    Levanta ``ghcr.io/github/github-mcp-server`` vía Docker stdio; devuelve StructuredTools LangChain.

    ``allowed_repos``: reservado para políticas declarativas (manifest); no fuerza aislamiento
    sobre el MCP sin soporte servidor adicional.

    ``read_only``: si True, el servidor oficial omite herramientas de mutación (GITHUB_READ_ONLY=1).

    Args:
        toolsets_override: sobreescribe lista de toolsets (CSV, sin ``projects``).
    """
    del allowed_repos  # reservado; evitar herramienta estática lint

    if not _mcp_available():
        return []

    tok_key = token_env if (token_env or "").strip() else "GITHUB_TOKEN"
    token = os.environ.get(tok_key, "").strip()
    if not token:
        _log.warning(
            "GitHub MCP disabled: PAT missing (%s). See scripts/doctor.py.",
            tok_key,
        )
        return []

    try:
        from mcp.client.stdio import StdioServerParameters
    except ImportError:
        return []

    ts_eff = ((toolsets_override or "").strip() or github_mcp_toolsets_default())
    env_merged = github_mcp_merged_child_env(token, read_only=read_only, toolsets=ts_eff)

    server_params = StdioServerParameters(
        command="docker",
        args=github_docker_run_argv(read_only=read_only),
        env=env_merged,
    )

    try:
        from duckclaw.forge.skills.mcp_stdio_util import mcp_stdio_list_tools

        tools_specs = await mcp_stdio_list_tools(server_params)
    except Exception:
        _log.exception("GitHub MCP: docker stdio init or list_tools failed (read_only=%s)", read_only)
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


_READWRITE_IDS_DEFAULT = frozenset({"gitclaw"})
_READWRITE_IDS_EXTRA_ENV = "DUCKCLAW_GITHUB_MCP_READWRITE_WORKERS"


def github_worker_allows_mutating_mcp(logical_worker_id: str, worker_slug: Optional[str] = None) -> bool:
    """True si el id de worker puede usar MCP GitHub sin GITHUB_READ_ONLY."""
    extras_raw = os.environ.get(_READWRITE_IDS_EXTRA_ENV, "").strip()
    csv = {x.strip().lower() for x in extras_raw.split(",") if x.strip()}
    allow = set(_READWRITE_IDS_DEFAULT) | csv
    lw = (logical_worker_id or "").strip().lower()
    slug = (worker_slug or "").strip().lower()
    return lw in allow or slug in allow


def register_github_skill(
    tools_list: list[Any],
    manifest_github_config: Optional[dict] = None,
    *,
    mcp_read_only: bool | None = None,
    logical_worker_id: str = "",
    manifest_worker_slug: Optional[str] = None,
) -> None:
    """
    Registra herramientas GitHub MCP si ``manifest_github_config``.

    Si ``mcp_read_only`` es None, se deduce desde allowlist (gitclaw + env CSV).
    """
    if not manifest_github_config:
        return
    cfg = manifest_github_config if isinstance(manifest_github_config, dict) else {}

    cfg_ro = cfg.get("mcp_read_only")
    explicit_ro: Optional[bool] = None
    if cfg_ro is not None:
        explicit_ro = bool(cfg_ro)

    ro = mcp_read_only
    if ro is None and explicit_ro is not None:
        ro = explicit_ro
    elif ro is None:
        ro = not github_worker_allows_mutating_mcp(
            logical_worker_id,
            manifest_worker_slug or logical_worker_id,
        )

    toolsets_override = cfg.get("toolsets")
    if isinstance(toolsets_override, str):
        tls = toolsets_override.strip()
    else:
        tls = None

    try:
        gh_tools = _run_async_from_sync(
            connect_github_mcp(
                allowed_repos=cfg.get("allowed_repos"),
                token_env=str(cfg.get("token_env", "GITHUB_TOKEN") or "GITHUB_TOKEN"),
                hitl_destructive=cfg.get("hitl_destructive", True),
                read_only=bool(ro),
                toolsets_override=tls,
            )
        )
        tools_list.extend(gh_tools)
        if gh_tools:
            _log.info(
                "GitHub MCP: registered %d tools (mcp_read_only=%s)",
                len(gh_tools),
                bool(ro),
            )
    except Exception:
        _log.warning("register_github_skill failed", exc_info=True)
