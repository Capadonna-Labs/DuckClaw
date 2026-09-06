"""DB-first MCP connector bridge for worker LangGraph tools."""

from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

from duckclaw.admin_mcp_connectors import (
    list_worker_mcp_connectors,
    resolve_connector_bearer_token,
    resolve_worker_uid,
    tool_allowed_by_policy,
    validate_connector_egress,
)
from duckclaw.forge.skills.mcp_stdio_util import mcp_stdio_call_tool, mcp_stdio_list_tools

_log = logging.getLogger(__name__)


def _run_async_from_sync(coro: Any) -> Any:
    try:
        import asyncio

        loop = asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result()


def _mcp_available() -> bool:
    try:
        import mcp  # noqa: F401

        return True
    except ImportError:
        return False


def _public_tool_name(connector_id: str, tool_name: str) -> str:
    safe_connector = connector_id.replace("-", "_").replace(".", "_")
    if safe_connector.startswith("mcp_"):
        safe_connector = safe_connector[4:]
    safe_tool = tool_name.replace("-", "_").replace(".", "_")
    return f"mcp__{safe_connector}__{safe_tool}"


def _build_stdio_params(connector: dict[str, Any]) -> Any:
    from mcp.client.stdio import StdioServerParameters

    command = str(connector.get("launch_command") or "").strip()
    if not command:
        raise ValueError("launch_command required for stdio connector")
    args = [str(x) for x in connector.get("launch_args") or []]
    env = {str(k): str(v) for k, v in (connector.get("launch_env") or {}).items()}
    merged_env = {**dict(os.environ), **env}
    return StdioServerParameters(command=command, args=args, env=merged_env)


def _http_headers(db: Any, connector: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    kind = str(connector.get("auth_kind") or "none").strip().lower()
    if kind == "bearer":
        token = resolve_connector_bearer_token(db, connector)
        if token:
            headers["Authorization"] = f"Bearer {token}"
    return headers


async def _list_connector_tools(db: Any, connector: dict[str, Any]) -> list[Any]:
    validate_connector_egress(connector)
    transport = str(connector.get("transport") or "").strip().lower()
    if transport == "stdio":
        params = _build_stdio_params(connector)
        return await mcp_stdio_list_tools(params)
    if transport == "streamable_http":
        from duckclaw.forge.skills.mcp_http_util import mcp_http_list_tools
        from duckclaw.mcp_android_adb import resolve_connector_endpoint_url

        url = resolve_connector_endpoint_url(connector)
        return await mcp_http_list_tools(url, headers=_http_headers(db, connector))
    raise ValueError(f"unsupported transport: {transport}")


async def _call_connector_tool(
    db: Any,
    connector: dict[str, Any],
    tool_name: str,
    arguments: dict[str, Any],
) -> str:
    validate_connector_egress(connector)
    transport = str(connector.get("transport") or "").strip().lower()
    if transport == "stdio":
        params = _build_stdio_params(connector)
        return await mcp_stdio_call_tool(params, tool_name, arguments)
    if transport == "streamable_http":
        from duckclaw.forge.skills.mcp_http_util import mcp_http_call_tool
        from duckclaw.mcp_android_adb import resolve_connector_endpoint_url

        url = resolve_connector_endpoint_url(connector)
        headers = _http_headers(db, connector)
        from duckclaw.forge.skills.google_calendar_rest import (
            call_google_calendar_rest,
            uses_google_calendar_rest_fallback,
        )
        from duckclaw.forge.skills.google_gmail_rest import (
            call_google_gmail_rest,
            uses_google_gmail_rest_fallback,
        )
        from duckclaw.forge.skills.youtube_analytics_rest import (
            call_youtube_analytics_rest,
            uses_youtube_analytics_rest_fallback,
        )

        if uses_google_calendar_rest_fallback(connector):
            return await call_google_calendar_rest(tool_name, arguments, headers=headers)
        if uses_google_gmail_rest_fallback(connector):
            return await call_google_gmail_rest(tool_name, arguments, headers=headers)
        if uses_youtube_analytics_rest_fallback(connector):
            return await call_youtube_analytics_rest(tool_name, arguments, headers=headers)

        return await mcp_http_call_tool(
            url,
            tool_name,
            arguments,
            headers=headers,
        )
    raise ValueError(f"unsupported transport: {transport}")


def _wrap_connector_tool(
    db: Any,
    connector: dict[str, Any],
    tool_spec: Any,
) -> Optional[Any]:
    from duckclaw.forge.skills.mcp_tool_args_schema import mcp_input_schema_to_args_model
    from langchain_core.tools import StructuredTool

    remote_name = getattr(tool_spec, "name", None) or str(tool_spec)
    if not tool_allowed_by_policy(connector, str(remote_name)):
        return None

    public_name = _public_tool_name(str(connector.get("connector_id") or ""), str(remote_name))
    raw_schema = getattr(tool_spec, "inputSchema", None) or getattr(tool_spec, "input_schema", None)
    args_model = mcp_input_schema_to_args_model(
        raw_schema if isinstance(raw_schema, dict) else None,
        public_name,
    )

    def _sync_call(**kwargs: Any) -> str:
        validated = args_model(**kwargs)
        payload = validated.model_dump(exclude_none=True)
        raw = _run_async_from_sync(_call_connector_tool(db, connector, str(remote_name), payload))
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict) and parsed.get("error"):
                return raw
        except json.JSONDecodeError:
            pass
        return raw

    desc = getattr(tool_spec, "description", None) or f"MCP {connector.get('display_name')}: {remote_name}"
    connector_label = str(connector.get("display_name") or connector.get("connector_id") or "connector")
    desc = f"[MCP {connector_label}] {desc}"
    return StructuredTool.from_function(
        _sync_call,
        name=public_name,
        description=str(desc),
        args_schema=args_model,
        infer_schema=False,
    )


def _register_connector_tool_specs(
    db: Any,
    connector: dict[str, Any],
    specs: list[Any],
    tools: list[Any],
) -> int:
    added = 0
    for spec in specs:
        wrapped = _wrap_connector_tool(db, connector, spec)
        if wrapped is not None:
            tools.append(wrapped)
            added += 1
    return added


def _gmail_rest_fallback_specs_if_ready(db: Any, connector: dict[str, Any]) -> list[Any]:
    from duckclaw.forge.skills.google_gmail_rest import (
        gmail_rest_fallback_tool_specs,
        uses_google_gmail_rest_fallback,
    )

    if not uses_google_gmail_rest_fallback(connector):
        return []
    if not resolve_connector_bearer_token(db, connector):
        return []
    return gmail_rest_fallback_tool_specs()


def _youtube_analytics_rest_fallback_specs_if_ready(db: Any, connector: dict[str, Any]) -> list[Any]:
    from duckclaw.forge.skills.youtube_analytics_rest import (
        uses_youtube_analytics_rest_fallback,
        youtube_analytics_rest_fallback_tool_specs,
    )

    if not uses_youtube_analytics_rest_fallback(connector):
        return []
    if not resolve_connector_bearer_token(db, connector):
        return []
    return youtube_analytics_rest_fallback_tool_specs()


async def connect_worker_mcp_connectors(db: Any, *, worker_uid: str, tenant_id: str = "default") -> list[Any]:
    if not _mcp_available():
        return []
    connectors = list_worker_mcp_connectors(db, worker_uid=worker_uid, tenant_id=tenant_id)
    tools: list[Any] = []
    for connector in connectors:
        try:
            specs = await _list_connector_tools(db, connector)
        except Exception as exc:
            _log.warning(
                "MCP connector list_tools failed connector=%s: %s",
                connector.get("connector_id"),
                exc,
            )
            fallback = _gmail_rest_fallback_specs_if_ready(db, connector)
            if fallback:
                added = _register_connector_tool_specs(db, connector, fallback, tools)
                _log.info(
                    "Gmail REST fallback registered %d tools connector=%s",
                    added,
                    connector.get("connector_id"),
                )
                continue
            fallback = _youtube_analytics_rest_fallback_specs_if_ready(db, connector)
            if fallback:
                added = _register_connector_tool_specs(db, connector, fallback, tools)
                _log.info(
                    "YouTube Analytics REST fallback registered %d tools connector=%s",
                    added,
                    connector.get("connector_id"),
                )
            continue
        _register_connector_tool_specs(db, connector, specs, tools)
    return tools


def _open_catalog_db() -> Any:
    """Open gateway DuckDB read-only for MCP connector registry lookups."""
    from duckclaw import DuckClaw
    from duckclaw.gateway_db import get_gateway_db_path

    path = (get_gateway_db_path() or "").strip()
    if not path:
        raise FileNotFoundError("Gateway DuckDB path not configured")
    return DuckClaw(path, read_only=True, engine="python")


def worker_has_mcp_connector(
    *,
    worker_id: str,
    tenant_id: str = "default",
    connector_id: str = "mcp_higgsfield",
) -> bool:
    """True when worker has an active MCP grant with bearer auth configured."""
    if not worker_id:
        return False
    catalog_db = _open_catalog_db()
    try:
        worker_uid = resolve_worker_uid(catalog_db, worker_id=worker_id, tenant_id=tenant_id)
        if not worker_uid:
            return False
        for connector in list_worker_mcp_connectors(
            catalog_db, worker_uid=worker_uid, tenant_id=tenant_id
        ):
            if str(connector.get("connector_id") or "") != connector_id:
                continue
            kind = str(connector.get("auth_kind") or "none").strip().lower()
            if kind == "bearer":
                return bool(resolve_connector_bearer_token(catalog_db, connector))
            return True
    except Exception:
        _log.debug("worker_has_mcp_connector check failed worker=%s", worker_id, exc_info=True)
        return False
    finally:
        catalog_db.close()


def register_worker_mcp_connector_tools(
    tools_list: list[Any],
    *,
    db: Any,
    worker_id: str,
    tenant_id: str = "default",
) -> None:
    del db
    if not worker_id:
        return
    catalog_db = _open_catalog_db()
    try:
        worker_uid = resolve_worker_uid(catalog_db, worker_id=worker_id, tenant_id=tenant_id)
        if not worker_uid:
            _log.debug("MCP connectors: worker_uid not found worker=%s tenant=%s", worker_id, tenant_id)
            return
        connector_tools = _run_async_from_sync(
            connect_worker_mcp_connectors(catalog_db, worker_uid=worker_uid, tenant_id=tenant_id)
        )
        if connector_tools:
            tools_list.extend(connector_tools)
            _log.info(
                "MCP connectors registered %d tools for worker=%s",
                len(connector_tools),
                worker_id,
            )
        connectors = list_worker_mcp_connectors(
            catalog_db, worker_uid=worker_uid, tenant_id=tenant_id
        )
        from duckclaw.mcp_android_adb import connector_uses_adb_auth

        if any(
            connector_uses_adb_auth(c)
            or str(c.get("preset_id") or "").strip().lower() == "android"
            for c in connectors
        ):
            from duckclaw.forge.skills.mcp_android_adb_bridge import (
                register_android_adb_helper_tools,
            )

            register_android_adb_helper_tools(tools_list)
    except Exception:
        _log.warning("register_worker_mcp_connector_tools failed worker=%s", worker_id, exc_info=True)
    finally:
        catalog_db.close()


async def test_mcp_connector(db: Any, connector: dict[str, Any]) -> dict[str, Any]:
    specs = await _list_connector_tools(db, connector)
    tools: list[dict[str, str]] = []
    for spec in specs:
        name = str(getattr(spec, "name", "") or spec)
        if not tool_allowed_by_policy(connector, name):
            continue
        desc = str(getattr(spec, "description", "") or "")
        tools.append({"name": name, "description": desc})
    return {
        "ok": True,
        "connector_id": str(connector.get("connector_id") or ""),
        "transport": str(connector.get("transport") or ""),
        "tool_count": len(tools),
        "tools": tools[:50],
    }
