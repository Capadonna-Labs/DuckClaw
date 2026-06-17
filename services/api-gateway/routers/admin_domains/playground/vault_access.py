"""Resolución de bóveda DuckDB y apertura read-only para admin playground."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from fastapi import Request

from routers.admin_domains.admin_common import repo_root
from routers.admin_domains.playground.tenant_resolution import playground_telegram_user_id


def duckdb_paths_same(a: str, b: str) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return (a or "").strip() == (b or "").strip()


def playground_vault_db_path(
    team_ctx: dict[str, Any],
    worker_id: str | None = None,
) -> str:
    """Ruta .duckdb del vault del playground (misma lógica que invoke_chat)."""
    from duckclaw.gateway_db import resolve_env_duckdb_path
    from duckclaw.vaults import resolve_active_vault, resolve_template_vault_path, vault_scope_id_for_tenant
    from duckclaw.workers.manifest import load_manifest

    tid = str(team_ctx.get("tenant_id") or "default").strip() or "default"
    uid = str(team_ctx.get("telegram_user_id") or "").strip()
    if not uid:
        raw_chat = str(team_ctx.get("team_chat_id") or "").strip()
        from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session

        if raw_chat and not is_admin_ui_chat_session(raw_chat):
            uid = raw_chat
    if not uid:
        uid = playground_telegram_user_id(None) or "admin-playground"
    scope = vault_scope_id_for_tenant(tid)
    _, vault_path = resolve_active_vault(uid, scope)
    wid = re.sub(r"[^a-zA-Z0-9_-]", "", (worker_id or "").strip())
    if wid:
        try:
            spec = load_manifest(wid)
            tpl = resolve_template_vault_path(spec.forge_vault_binding, uid)
            if tpl:
                vault_path = tpl
        except Exception:
            pass
    return resolve_env_duckdb_path(str(vault_path or "").strip())


def open_playground_vault_db(vault_path: str, *, read_only: bool = True) -> Any:
    from duckclaw import DuckClaw
    from duckclaw.gateway_db import get_gateway_db_path, resolve_env_duckdb_path
    from duckclaw.spawn_profile import spawn_inline_writes_enabled

    abs_path = vault_path
    if not os.path.isabs(abs_path):
        abs_path = str(repo_root() / vault_path.lstrip("/"))
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(abs_path)
    is_read_only = read_only
    if read_only and spawn_inline_writes_enabled():
        try:
            gw = resolve_env_duckdb_path(get_gateway_db_path())
            if Path(abs_path).resolve() == Path(gw).resolve():
                is_read_only = False
        except OSError:
            pass
    return DuckClaw(abs_path, read_only=is_read_only, engine="python")


async def resolved_vault_for_admin_chat(
    chat_id: str,
    team_ctx: dict[str, Any],
    worker_id: str | None,
    *,
    body_override: str | None = None,
    request: Request | None = None,
    runtime_default_vault: str | None = None,
) -> dict[str, Any]:
    """Bóveda efectiva: body > meta conversación > runtime DB-first > worker/activa."""
    from duckclaw.gateway_db import resolve_env_duckdb_path

    cid = (chat_id or "").strip()
    override = (body_override or "").strip()
    scope = "default"
    if not override and request is not None:
        redis_client = getattr(request.app.state, "redis", None)
        if redis_client is not None and cid:
            from core.admin_conversations import get_conversation_meta

            tid = str(team_ctx.get("tenant_id") or "default").strip() or "default"
            meta = await get_conversation_meta(redis_client, tid, cid)
            if meta is not None and (meta.vault_db_path or "").strip():
                override = (meta.vault_db_path or "").strip()
                scope = "chat"
    elif override:
        scope = "chat"
    try:
        default_path = playground_vault_db_path(team_ctx, worker_id)
    except Exception:
        default_path = ""
    runtime_default = (runtime_default_vault or "").strip()
    if not override and runtime_default:
        runtime_effective = resolve_env_duckdb_path(runtime_default)
        if os.path.isfile(runtime_effective):
            return {
                "effective_path": runtime_effective,
                "scope": "runtime",
                "override_path": None,
                "default_path": runtime_default,
            }
    effective = resolve_env_duckdb_path(override or default_path)
    return {
        "effective_path": effective,
        "scope": scope,
        "override_path": override or None,
        "default_path": default_path or None,
    }
