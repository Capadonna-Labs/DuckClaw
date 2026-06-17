"""Kanban typed write handlers."""
from __future__ import annotations

import json
import uuid
from typing import Any


def _kanban_tags_json(raw: Any) -> str:
    tags = raw if isinstance(raw, list) else []
    clean = []
    for tag in tags:
        text = str(tag).strip()
        if text and text not in clean:
            clean.append(text[:64])
        if len(clean) >= 16:
            break
    return json.dumps(clean, ensure_ascii=False)


def _kanban_event(conn: Any, *, card_id: str, event_type: str, actor_email: str, payload: dict) -> None:
    conn.execute(
        "INSERT INTO main.admin_kanban_events "
        "(event_id, card_id, event_type, payload_json, actor_email) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            f"evt_{uuid.uuid4().hex[:16]}",
            card_id,
            event_type,
            json.dumps(payload, ensure_ascii=False, default=str),
            actor_email,
        ],
    )


def _apply_upsert_kanban_card(conn: Any, payload: dict) -> None:
    card_id = str(payload["card_id"]).strip()
    if not card_id:
        raise ValueError("card_id required")

    tenant_id = str(payload.get("tenant_id", "default") or "default").strip() or "default"
    actor_email = str(payload.get("actor_email", "system") or "system").strip() or "system"
    title = str(payload.get("title") or "").strip()[:120]
    if not title:
        raise ValueError("title required")
    description = str(payload.get("description") or "").strip()[:2000]
    status = str(payload.get("status") or "todo").strip()
    if status not in {"todo", "in_progress", "done", "cancelled"}:
        raise ValueError(f"Invalid kanban status: {status}")
    priority = int(payload.get("priority") or 0)
    sort_order = int(payload.get("sort_order") or 0)
    worker_id = str(payload.get("worker_id") or "").strip()[:128]
    tags_json = _kanban_tags_json(payload.get("tags"))

    existing = conn.execute(
        "SELECT tenant_id, actor_email FROM main.admin_kanban_cards WHERE card_id = ?",
        [card_id],
    ).fetchone()
    if existing and (str(existing[0]) != tenant_id or str(existing[1]) != actor_email):
        raise ValueError("Kanban card not found for tenant/actor")

    if existing:
        conn.execute(
            "UPDATE main.admin_kanban_cards "
            "SET title = ?, description = ?, status = ?, priority = ?, sort_order = ?, "
            "assignee_email = ?, tags_json = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE card_id = ?",
            [title, description, status, priority, sort_order, worker_id, tags_json, card_id],
        )
        event_type = "kanban_card.updated"
    else:
        conn.execute(
            "INSERT INTO main.admin_kanban_cards "
            "(card_id, tenant_id, actor_email, title, description, status, priority, sort_order, "
            "assignee_email, tags_json) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [card_id, tenant_id, actor_email, title, description, status, priority, sort_order, worker_id, tags_json],
        )
        event_type = "kanban_card.created"

    _kanban_event(
        conn,
        card_id=card_id,
        event_type=event_type,
        actor_email=actor_email,
        payload={"status": status, "title": title, "worker_id": worker_id},
    )


def _apply_delete_kanban_card(conn: Any, payload: dict) -> None:
    card_id = str(payload["card_id"]).strip()
    if not card_id:
        raise ValueError("card_id required")

    tenant_id = str(payload.get("tenant_id", "default") or "default").strip() or "default"
    actor_email = str(payload.get("actor_email", "system") or "system").strip() or "system"
    row = conn.execute(
        "SELECT title, status FROM main.admin_kanban_cards "
        "WHERE card_id = ? AND tenant_id = ? AND actor_email = ?",
        [card_id, tenant_id, actor_email],
    ).fetchone()
    if not row:
        raise ValueError("Kanban card not found")

    conn.execute("DELETE FROM main.admin_kanban_cards WHERE card_id = ?", [card_id])
    _kanban_event(
        conn,
        card_id=card_id,
        event_type="kanban_card.deleted",
        actor_email=actor_email,
        payload={"title": row[0], "status": row[1]},
    )


from duckclaw.write_handlers.registry import register_handler

register_handler("upsert_kanban_card", _apply_upsert_kanban_card)
register_handler("delete_kanban_card", _apply_delete_kanban_card)
