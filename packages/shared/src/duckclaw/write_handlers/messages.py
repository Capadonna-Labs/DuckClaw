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


def _apply_create_contact_invite(conn: Any, payload: dict) -> None:
    conn.execute(
        "INSERT INTO main.admin_contact_invites (invite_id, owner_email, secret_hash, expires_at) VALUES (?, ?, ?, ?::TIMESTAMP) "
        "ON CONFLICT (invite_id) DO NOTHING",
        [payload["invite_id"], _actor(payload), payload["secret_hash"], payload["expires_at"]],
    )


def _apply_accept_contact_invite(conn: Any, payload: dict) -> None:
    row = conn.execute(
        "SELECT owner_email FROM main.admin_contact_invites WHERE invite_id = ? AND secret_hash = ? AND used_at IS NULL "
        "AND expires_at > CAST(CURRENT_TIMESTAMP AS TIMESTAMP)",
        [payload["invite_id"], payload["secret_hash"]],
    ).fetchone()
    if not row:
        raise ValueError("Invitación inválida, usada o vencida")
    remote = str(payload["remote_email"]).strip().lower()
    if conn.execute("SELECT 1 FROM main.admin_console_users WHERE lower(email) = ?", [remote]).fetchone():
        raise ValueError("ese correo es de un usuario de esta instancia")   # a contact must never act as a local user
    conn.execute("UPDATE main.admin_contact_invites SET used_at = CURRENT_TIMESTAMP WHERE invite_id = ?", [payload["invite_id"]])
    conn.execute(
        "INSERT INTO main.admin_contacts (contact_id, owner_email, role, remote_email, remote_name, token_hash) VALUES (?, ?, 'host', ?, ?, ?)",
        [payload["contact_id"], row[0], remote, str(payload.get("remote_name") or "")[:80], payload["token_hash"]],
    )


def _apply_add_guest_contact(conn: Any, payload: dict) -> None:
    conn.execute(
        "INSERT INTO main.admin_contacts (contact_id, owner_email, role, remote_url, remote_email, remote_name, token) "
        "VALUES (?, ?, 'guest', ?, ?, ?, ?) ON CONFLICT (contact_id) DO NOTHING",
        [payload["contact_id"], _actor(payload), str(payload["remote_url"]).rstrip("/"), str(payload["remote_email"]).lower(),
         str(payload.get("remote_name") or "")[:80], payload["token"]],
    )


def _apply_delete_contact(conn: Any, payload: dict) -> None:
    if not conn.execute("SELECT 1 FROM main.admin_contacts WHERE contact_id = ? AND owner_email = ?", [payload["contact_id"], _actor(payload)]).fetchone():
        raise ValueError("Contacto no encontrado")
    conn.execute("DELETE FROM main.admin_contacts WHERE contact_id = ?", [payload["contact_id"]])


from duckclaw.write_handlers.registry import register_handler  # noqa: E402

register_handler("create_channel", _apply_create_channel)
register_handler("post_channel_message", _apply_post_channel_message)
register_handler("create_contact_invite", _apply_create_contact_invite)
register_handler("accept_contact_invite", _apply_accept_contact_invite)
register_handler("add_guest_contact", _apply_add_guest_contact)
register_handler("delete_contact", _apply_delete_contact)
