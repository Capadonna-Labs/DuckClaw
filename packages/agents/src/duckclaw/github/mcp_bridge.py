"""
Generic GitHub MCP capability.

This module is intentionally outside ``duckclaw.forge.skills`` and contains no
Job Hunter or deterministic PR workflow. Workers must opt in via DB-first
capability/config before these tools are registered.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from duckclaw.forge.skills.mcp_tool_args_schema import mcp_input_schema_to_args_model

_log = logging.getLogger(__name__)

_GITHUB_IMAGE_DEFAULT = "ghcr.io/github/github-mcp-server"
_TOOLSETS_DEFAULT = "repos,issues,pull_requests,actions,code_security"
_READWRITE_IDS_EXTRA_ENV = "DUCKCLAW_GITHUB_MCP_READWRITE_WORKERS"

_REPO_SCOPED_GITHUB_TOOLS = frozenset(
    {
        "get_file_contents",
        "search_code",
        "search_repositories",
        "list_branches",
        "list_commits",
        "create_or_update_file",
        "push_files",
        "create_pull_request",
        "delete_file",
        "list_issues",
        "get_issue",
        "list_pull_requests",
        "get_pull_request",
    }
)
_DESTRUCTIVE_TOOLS = frozenset(
    {
        "github_delete_branch",
        "github_merge_pr",
        "github_force_push",
        "delete_branch",
        "merge_pr",
        "force_push",
    }
)
_MUTATING_GITHUB_TOOLS = frozenset(
    {
        "create_or_update_file",
        "push_files",
        "create_pull_request",
        "delete_file",
        "update_issue",
        "create_issue",
    }
)
_WRITE_GITHUB_TOOL_NAMES = frozenset(
    {
        "create_or_update_file",
        "push_files",
        "create_pull_request",
        "delete_file",
    }
)
_PROTECTED_GIT_BRANCHES = frozenset({"main", "master"})


def _github_branch_from_payload(payload: dict[str, Any]) -> str:
    for key in ("branch", "ref", "head", "base"):
        raw = str(payload.get(key) or "").strip()
        if not raw:
            continue
        if raw.startswith("refs/heads/"):
            return raw.split("/", 2)[-1].strip().lower()
        return raw.lower()
    return ""


def reject_protected_branch_mutation(tool_name: str, payload: dict[str, Any]) -> str | None:
    if tool_name not in _MUTATING_GITHUB_TOOLS:
        return None
    branch = _github_branch_from_payload(payload)
    if branch in _PROTECTED_GIT_BRANCHES:
        return (
            f"Zero-Trust: mutación en rama protegida '{branch}' bloqueada. "
            "Usa una rama feature y aprobación humana antes de abrir PR."
        )
    return None


def github_runtime_owner_repo() -> tuple[str, str]:
    owner = (
        os.environ.get("GITHUB_OWNER") or os.environ.get("DUCKCLAW_GITHUB_OWNER") or ""
    ).strip()
    repo = (
        os.environ.get("GITHUB_REPO") or os.environ.get("DUCKCLAW_GITHUB_REPO") or ""
    ).strip()
    return owner, repo


def apply_github_repo_scope(tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
    if tool_name not in _REPO_SCOPED_GITHUB_TOOLS:
        return payload
    owner, repo = github_runtime_owner_repo()
    if not owner or not repo:
        return payload

    scoped = dict(payload)
    scoped["owner"] = owner
    scoped["repo"] = repo
    if tool_name == "search_code":
        query_key = "query" if "query" in scoped else "q" if "q" in scoped else "query"
        raw_query = str(scoped.get(query_key) or "").strip()
        repo_token = f"repo:{owner}/{repo}"
        if repo_token.lower() not in raw_query.lower():
            scoped[query_key] = f"{repo_token} {raw_query}".strip() if raw_query else repo_token
    return scoped


def github_mcp_toolsets_default() -> str:
    raw = (os.environ.get("GITHUB_TOOLSETS") or "").strip()
    return raw or _TOOLSETS_DEFAULT


def github_mcp_image_ref() -> str:
    ref = (os.environ.get("DUCKCLAW_GITHUB_MCP_IMAGE") or _GITHUB_IMAGE_DEFAULT).strip()
    return ref or _GITHUB_IMAGE_DEFAULT


def github_docker_run_argv(*, read_only: bool) -> list[str]:
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


def github_mcp_merged_child_env(
    token: str,
    *,
    read_only: bool,
    toolsets: Optional[str] = None,
) -> dict[str, str]:
    base = dict(os.environ)
    if not read_only:
        base.pop("GITHUB_READ_ONLY", None)
    base["GITHUB_PERSONAL_ACCESS_TOKEN"] = token
    base["GITHUB_TOOLSETS"] = (toolsets or "").strip() or github_mcp_toolsets_default()
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
    from mcp.client.stdio import StdioServerParameters

    return StdioServerParameters(
        command="docker",
        args=github_docker_run_argv(read_only=read_only),
        env=github_mcp_merged_child_env(token, read_only=read_only, toolsets=toolsets),
    )


def _run_async_from_sync(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


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
    read_only: bool = True,
    toolsets_override: Optional[str] = None,
) -> list[Any]:
    del allowed_repos

    if not _mcp_available():
        return []

    tok_key = token_env if (token_env or "").strip() else "GITHUB_TOKEN"
    token = os.environ.get(tok_key, "").strip()
    if not token:
        _log.warning("GitHub MCP disabled: PAT missing (%s).", tok_key)
        return []

    try:
        from mcp.client.stdio import StdioServerParameters
    except ImportError:
        return []

    server_params = StdioServerParameters(
        command="docker",
        args=github_docker_run_argv(read_only=read_only),
        env=github_mcp_merged_child_env(
            token,
            read_only=read_only,
            toolsets=toolsets_override,
        ),
    )

    try:
        from duckclaw.forge.skills.mcp_stdio_util import mcp_stdio_list_tools

        tool_specs = await mcp_stdio_list_tools(server_params)
    except Exception:
        _log.exception("GitHub MCP init or list_tools failed (read_only=%s)", read_only)
        return []

    result: list[Any] = []
    for spec in tool_specs:
        name = getattr(spec, "name", None) or str(spec)
        if read_only and name in _WRITE_GITHUB_TOOL_NAMES:
            continue
        is_destructive = any(marker in name.lower() for marker in _DESTRUCTIVE_TOOLS)
        tool = (
            _wrap_with_hitl(spec, name)
            if is_destructive and hitl_destructive
            else _mcp_tool_to_structured(server_params, spec, name)
        )
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
        payload = apply_github_repo_scope(name, validated.model_dump(exclude_none=True))
        branch_err = reject_protected_branch_mutation(name, payload)
        if branch_err:
            return json.dumps({"error": branch_err}, ensure_ascii=False)
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
        del kwargs
        return (
            f"[HITL] La acción {name} requiere aprobación del usuario. "
            "Usa /approve para confirmar, o /reject para cancelar."
        )

    desc = (getattr(tool_spec, "description", None) or f"GitHub MCP: {name}") + " [Requiere /approve]"
    return StructuredTool.from_function(
        _call_hitl,
        name=name,
        description=desc,
        args_schema=args_model,
        infer_schema=False,
    )


def _github_worker_id_key(worker_id: str) -> str:
    return (worker_id or "").strip().lower().replace("-", "_")


def github_worker_allows_mutating_mcp(
    logical_worker_id: str,
    worker_slug: Optional[str] = None,
) -> bool:
    extras_raw = os.environ.get(_READWRITE_IDS_EXTRA_ENV, "").strip()
    allow = {_github_worker_id_key(x) for x in extras_raw.split(",") if x.strip()}
    logical = _github_worker_id_key(logical_worker_id)
    slug = _github_worker_id_key(worker_slug or "")
    return logical in allow or slug in allow


def register_github_skill(
    tools_list: list[Any],
    manifest_github_config: Optional[dict] = None,
    *,
    mcp_read_only: bool | None = None,
    logical_worker_id: str = "",
    manifest_worker_slug: Optional[str] = None,
) -> None:
    if manifest_github_config is None:
        return
    cfg = manifest_github_config if isinstance(manifest_github_config, dict) else {}

    cfg_ro = cfg.get("mcp_read_only")
    explicit_ro = bool(cfg_ro) if cfg_ro is not None else None
    if mcp_read_only is not None:
        read_only = bool(mcp_read_only)
    elif explicit_ro is not None:
        read_only = explicit_ro
    else:
        read_only = not github_worker_allows_mutating_mcp(
            logical_worker_id,
            manifest_worker_slug or logical_worker_id,
        )

    toolsets_override = cfg.get("toolsets")
    toolsets = toolsets_override.strip() if isinstance(toolsets_override, str) else None

    try:
        gh_tools = _run_async_from_sync(
            connect_github_mcp(
                allowed_repos=cfg.get("allowed_repos"),
                token_env=str(cfg.get("token_env", "GITHUB_TOKEN") or "GITHUB_TOKEN"),
                hitl_destructive=cfg.get("hitl_destructive", True),
                read_only=read_only,
                toolsets_override=toolsets,
            )
        )
        tools_list.extend(gh_tools)
        if gh_tools:
            _log.info("GitHub MCP registered %d tools (read_only=%s)", len(gh_tools), read_only)
    except Exception:
        _log.warning("register_github_skill failed", exc_info=True)
