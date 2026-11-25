"""Messages typed write handlers: direct messages and groups between console users."""
from __future__ import annotations

import json
from typing import Any


def _actor(payload: dict) -> str:
    actor = str(payload.get("actor_email") or "").strip().lower()
    if "@" not in actor:
        raise ValueError("actor_email requerido")
    return actor


def _apply_create_channel(conn: Any, payload: dict) -> None:
    actor = _actor(payload)
    members = sorted({str(m).strip().lower() for m in payload.get("members") or [] if str(m).strip()} | {actor})
    kind = str(payload.get("kind") or "group")
    if kind == "dm" and len(members) != 2:
        raise ValueError("un mensaje directo tiene exactamente dos personas")
    if conn.execute("SELECT 1 FROM main.admin_channels WHERE channel_id = ?", [payload["channel_id"]]).fetchone():
        return   # idempotent replay
    conn.execute(
        "INSERT INTO main.admin_channels (channel_id, kind, name, members_json, created_by) VALUES (?, ?, ?, ?, ?)",
        [payload["channel_id"], kind, str(payload.get("name") or "")[:80], json.dumps(members), actor],
    )


def _apply_post_channel_message(conn: Any, payload: dict) -> None:
    actor = _actor(payload)
    row = conn.execute("SELECT members_json FROM main.admin_channels WHERE channel_id = ?", [payload["channel_id"]]).fetchone()
    if not row or actor not in json.loads(row[0] or "[]"):
        raise ValueError("Canal no encontrado o no eres miembro")
    conn.execute(
        "INSERT INTO main.admin_channel_messages (message_id, channel_id, author_email, author_label, body) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (message_id) DO NOTHING",
        [payload["message_id"], payload["channel_id"], actor, str(payload.get("author_label") or "")[:60], str(payload["body"])[:8000]],
    )
    conn.execute("UPDATE main.admin_channels SET updated_at = CURRENT_TIMESTAMP WHERE channel_id = ?", [payload["channel_id"]])


from duckclaw.write_handlers.registry import register_handler  # noqa: E402

register_handler("create_channel", _apply_create_channel)
register_handler("post_channel_message", _apply_post_channel_message)
