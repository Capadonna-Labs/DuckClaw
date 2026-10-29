"""Worlds typed write handlers: self-hosted worlds and their bots (DuckClaw stores the configuration, the extension's runner reports the status)."""
from __future__ import annotations

import json
from typing import Any


def _scope(payload: dict) -> tuple[str, str]:
    return (str(payload.get("tenant_id", "default") or "default").strip() or "default",
            str(payload.get("actor_email", "system") or "system").strip() or "system")


def _json_text(value: Any) -> str:
    return json.dumps(value if isinstance(value, dict) else {}, ensure_ascii=False, default=str)


def _apply_upsert_world(conn: Any, payload: dict) -> None:
    world_id = str(payload["world_id"]).strip()
    name = str(payload.get("name") or "").strip()[:80]
    if not world_id or not name:
        raise ValueError("world_id and name required")
    tenant_id, actor = _scope(payload)
    row = conn.execute("SELECT tenant_id, actor_email FROM main.admin_worlds WHERE world_id = ?", [world_id]).fetchone()
    if row and (str(row[0]), str(row[1])) != (tenant_id, actor):
        raise ValueError("World not found for tenant/actor")
    args = [name, str(payload.get("kind") or "generic"), str(payload.get("host") or ""), payload.get("port"),
            _json_text(payload.get("config")), bool(payload.get("enabled", True))]
    if row:
        conn.execute("UPDATE main.admin_worlds SET name = ?, kind = ?, host = ?, port = ?, config_json = ?, enabled = ?, updated_at = CURRENT_TIMESTAMP "
                     "WHERE world_id = ?", [*args, world_id])
    else:
        conn.execute("INSERT INTO main.admin_worlds (world_id, tenant_id, actor_email, name, kind, host, port, config_json, enabled) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [world_id, tenant_id, actor, *args])


def _apply_delete_world(conn: Any, payload: dict) -> None:
    world_id = str(payload["world_id"]).strip()
    tenant_id, actor = _scope(payload)
    if not conn.execute("SELECT 1 FROM main.admin_worlds WHERE world_id = ? AND tenant_id = ? AND actor_email = ?", [world_id, tenant_id, actor]).fetchone():
        raise ValueError("World not found")
    conn.execute("DELETE FROM main.admin_world_bots WHERE world_id = ? AND tenant_id = ? AND actor_email = ?", [world_id, tenant_id, actor])
    conn.execute("DELETE FROM main.admin_worlds WHERE world_id = ?", [world_id])


def _apply_upsert_world_bot(conn: Any, payload: dict) -> None:
    bot_id, world_id = str(payload["bot_id"]).strip(), str(payload["world_id"]).strip()
    name = str(payload.get("name") or "").strip()[:48]
    if not bot_id or not world_id or not name:
        raise ValueError("bot_id, world_id and name required")
    tenant_id, actor = _scope(payload)
    if not conn.execute("SELECT 1 FROM main.admin_worlds WHERE world_id = ? AND tenant_id = ? AND actor_email = ?", [world_id, tenant_id, actor]).fetchone():
        raise ValueError("World not found for tenant/actor")
    row = conn.execute("SELECT tenant_id, actor_email FROM main.admin_world_bots WHERE bot_id = ?", [bot_id]).fetchone()
    if row and (str(row[0]), str(row[1])) != (tenant_id, actor):
        raise ValueError("Bot not found for tenant/actor")
    args = [world_id, name, str(payload.get("worker_id") or "")[:128], _json_text(payload.get("settings")), bool(payload.get("enabled", True))]
    if row:   # status and last_seen_at are the runner's: an edit never touches them
        conn.execute("UPDATE main.admin_world_bots SET world_id = ?, name = ?, worker_id = ?, settings_json = ?, enabled = ?, updated_at = CURRENT_TIMESTAMP "
                     "WHERE bot_id = ?", [*args, bot_id])
    else:
        conn.execute("INSERT INTO main.admin_world_bots (bot_id, tenant_id, actor_email, world_id, name, worker_id, settings_json, enabled) "
                     "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [bot_id, tenant_id, actor, *args])


def _apply_delete_world_bot(conn: Any, payload: dict) -> None:
    tenant_id, actor = _scope(payload)
    bot_id = str(payload["bot_id"]).strip()
    if not conn.execute("SELECT 1 FROM main.admin_world_bots WHERE bot_id = ? AND tenant_id = ? AND actor_email = ?", [bot_id, tenant_id, actor]).fetchone():
        raise ValueError("Bot not found")
    conn.execute("DELETE FROM main.admin_world_bots WHERE bot_id = ?", [bot_id])


def _apply_report_world_bot_status(conn: Any, payload: dict) -> None:
    tenant_id, actor = _scope(payload)
    bot_id = str(payload["bot_id"]).strip()
    if not conn.execute("SELECT 1 FROM main.admin_world_bots WHERE bot_id = ? AND tenant_id = ? AND actor_email = ?", [bot_id, tenant_id, actor]).fetchone():
        raise ValueError("Bot not found")
    conn.execute("UPDATE main.admin_world_bots SET status = ?, status_detail = ?, last_seen_at = CURRENT_TIMESTAMP WHERE bot_id = ?",
                 [str(payload.get("status") or "unknown"), str(payload.get("detail") or "")[:300], bot_id])


from duckclaw.write_handlers.registry import register_handler

register_handler("upsert_world", _apply_upsert_world)
register_handler("delete_world", _apply_delete_world)
register_handler("upsert_world_bot", _apply_upsert_world_bot)
register_handler("delete_world_bot", _apply_delete_world_bot)
register_handler("report_world_bot_status", _apply_report_world_bot_status)
