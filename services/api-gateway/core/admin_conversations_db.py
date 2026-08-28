"""Persistencia durable de conversaciones admin en DuckDB (fuente de verdad).

Tablas: ``main.admin_conversations`` + ``main.admin_conversation_messages``.
Redis / LiteSessionStore quedan como caché best-effort.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

_log = logging.getLogger(__name__)

_PREVIEW_MAX = 120
_TITLE_MAX = 80


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _sql_lit(v: str, max_len: int = 8192) -> str:
    return (v or "").replace("'", "''")[:max_len]


def _preview_text(text: str) -> str:
    t = " ".join((text or "").split())
    if len(t) > _PREVIEW_MAX:
        return t[: _PREVIEW_MAX - 1] + "…"
    return t


def _is_system_turn_title(text: str) -> bool:
    """True si el texto es turno sistema /loop, no un título de hilo."""
    t = " ".join((text or "").split())
    if not t:
        return False
    low = t.lower()
    if low.startswith("[ciclo loop]") or low.startswith("[ciclo meditate]"):
        return True
    if t.startswith("[SYSTEM_EVENT"):
        return True
    return False


def _title_from_first_message(text: str) -> str:
    t = " ".join((text or "").split())
    if not t or _is_system_turn_title(t):
        return ""
    if len(t) > _TITLE_MAX:
        return t[: _TITLE_MAX - 1].rstrip() + "…"
    return t


def _is_generic_conversation_title(title: str) -> bool:
    import re

    t = (title or "").strip()
    if _is_system_turn_title(t):
        return True
    return bool(re.fullmatch(r"Conversación \d{4}-\d{2}-\d{2}", t))


def _fetch_dicts(db: Any, sql: str) -> list[dict[str, Any]]:
    try:
        from duckclaw.shared_db_grants import _query_all_dicts

        return _query_all_dicts(db, sql)
    except Exception as exc:
        _log.debug("admin_conversations_db: query failed: %s", exc)
        return []


def _open_db(*, read_only: bool = False):
    from core.admin_identity import open_gateway_db

    return open_gateway_db(read_only=read_only)


def _hub_db_path() -> str:
    from duckclaw.gateway_db import get_gateway_db_path

    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise FileNotFoundError("Gateway DuckDB no disponible")
    return gw


def _writes_via_db_writer() -> bool:
    from duckclaw.spawn_profile import spawn_inline_writes_enabled

    return not spawn_inline_writes_enabled()


def _execute_hub_write(sql: str | Sequence[str]) -> None:
    """Hub writes via db-writer when Gateway is RO-only (avoids mixed RO/RW in one PID).

    Statements are sent as a single task: the writer wraps them in one transaction
    and one RW connection. Splitting them costs an exclusive DuckDB lock per row and
    lets a DELETE commit without its INSERTs.
    """
    statements = [sql] if isinstance(sql, str) else list(sql)
    statements = [s.strip().rstrip(";") for s in statements if (s or "").strip()]
    if not statements:
        return
    if _writes_via_db_writer():
        from duckclaw.db_write_queue import enqueue_duckdb_write_sync

        enqueue_duckdb_write_sync(
            db_path=_hub_db_path(),
            query=";\n".join(statements),
            user_id="default",
            tenant_id="default",
        )
        return
    with _open_db(read_only=False) as db:
        ensure_admin_conversation_columns(db)
        for statement in statements:
            db.execute(statement)


def ensure_admin_conversation_columns(db: Any) -> None:
    """Idempotent column ensure (covers hubs that lag migration 38)."""
    if getattr(db, "_read_only", False):
        return
    alters = (
        "ALTER TABLE main.admin_conversations ADD COLUMN IF NOT EXISTS section VARCHAR DEFAULT ''",
        "ALTER TABLE main.admin_conversations ADD COLUMN IF NOT EXISTS last_worker_id VARCHAR DEFAULT ''",
        "ALTER TABLE main.admin_conversations ADD COLUMN IF NOT EXISTS preferred_worker_id VARCHAR DEFAULT ''",
        "ALTER TABLE main.admin_conversations ADD COLUMN IF NOT EXISTS workers_json TEXT DEFAULT '[]'",
        "ALTER TABLE main.admin_conversations ADD COLUMN IF NOT EXISTS last_message_preview VARCHAR DEFAULT ''",
        "ALTER TABLE main.admin_conversations ADD COLUMN IF NOT EXISTS message_count INTEGER DEFAULT 0",
        "ALTER TABLE main.admin_conversations ADD COLUMN IF NOT EXISTS origin VARCHAR DEFAULT 'admin_ui'",
    )
    for stmt in alters:
        try:
            db.execute(stmt)
        except Exception:
            pass


def _row_to_meta(row: dict[str, Any]):
    from core.admin_conversations import AdminConversationMeta

    workers_raw = row.get("workers_json") or "[]"
    workers: list[str] = []
    if isinstance(workers_raw, list):
        workers = [str(w) for w in workers_raw if str(w).strip()]
    else:
        try:
            parsed = json.loads(str(workers_raw) or "[]")
            if isinstance(parsed, list):
                workers = [str(w) for w in parsed if str(w).strip()]
        except Exception:
            workers = []
    last_worker = str(row.get("last_worker_id") or row.get("worker_id") or "").strip()
    preferred = str(row.get("preferred_worker_id") or "").strip()
    created = row.get("created_at")
    updated = row.get("updated_at")
    created_s = created.strftime("%Y-%m-%dT%H:%M:%SZ") if hasattr(created, "strftime") else str(created or "")
    updated_s = updated.strftime("%Y-%m-%dT%H:%M:%SZ") if hasattr(updated, "strftime") else str(updated or "")
    return AdminConversationMeta(
        session_id=str(row.get("conversation_id") or "").strip(),
        tenant_id=str(row.get("tenant_id") or "default").strip() or "default",
        title=str(row.get("title") or "").strip(),
        created_at=created_s,
        updated_at=updated_s,
        actor=str(row.get("actor_email") or "").strip(),
        section=str(row.get("section") or "").strip(),
        last_worker_id=last_worker,
        preferred_worker_id=preferred,
        workers=workers,
        last_message_preview=str(row.get("last_message_preview") or "").strip(),
        message_count=int(row.get("message_count") or 0),
        origin=str(row.get("origin") or "admin_ui").strip() or "admin_ui",
        vault_db_path=str(row.get("vault_path") or "").strip(),
    )


def db_get_conversation_meta(tenant_id: str, session_id: str):
    tid = (tenant_id or "default").strip() or "default"
    sid = (session_id or "").strip()
    if not sid:
        return None
    try:
        with _open_db(read_only=True) as db:
            ensure_admin_conversation_columns(db)
            rows = _fetch_dicts(
                db,
                "SELECT * FROM main.admin_conversations "
                f"WHERE tenant_id = '{_sql_lit(tid, 128)}' "
                f"AND conversation_id = '{_sql_lit(sid, 128)}' "
                "LIMIT 1",
            )
            if not rows:
                return None
            return _row_to_meta(rows[0])
    except FileNotFoundError:
        return None
    except Exception as exc:
        _log.warning("admin_conversations_db: get meta %s/%s: %s", tid, sid, exc)
        return None


def db_upsert_conversation_meta(
    *,
    tenant_id: str,
    session_id: str,
    actor: str = "",
    section: str | None = None,
    last_worker_id: str = "",
    preferred_worker_id: str | None = None,
    workers: list[str] | None = None,
    user_message: str = "",
    assistant_message: str = "",
    message_count: int | None = None,
    title: str | None = None,
    vault_db_path: str | None = None,
    origin: str = "admin_ui",
    existing: Any = None,
):
    from core.admin_conversations import derive_section_from_session_id, should_index_admin_conversation

    if not should_index_admin_conversation(session_id):
        return None
    tid = (tenant_id or "default").strip() or "default"
    sid = (session_id or "").strip()
    if not sid:
        return None
    now = _now_iso()
    if existing is None:
        existing = db_get_conversation_meta(tid, sid)
    sec = derive_section_from_session_id(sid, origin_section=section)
    lw = (last_worker_id or "").strip()
    worker_list = list(workers) if workers is not None else (list(existing.workers) if existing else [])
    if lw and lw not in worker_list:
        worker_list.append(lw)
    preferred = (
        preferred_worker_id
        if preferred_worker_id is not None
        else (existing.preferred_worker_id if existing else "")
    )
    preferred = (preferred or "").strip()
    preview_src = (assistant_message or user_message or "").strip()
    preview = _preview_text(preview_src)

    # If the row exists but this process failed to read it (hub lock), INSERT
    # ON CONFLICT must not replace a custom title with the last user message.
    update_title_on_conflict = False
    if existing:
        next_title = existing.title
        if title and title.strip():
            next_title = title.strip()
            update_title_on_conflict = True
        elif _is_generic_conversation_title(existing.title):
            auto = _title_from_first_message(user_message)
            if auto:
                next_title = auto
                update_title_on_conflict = True
        next_count = (
            message_count
            if message_count is not None
            else existing.message_count + (1 if user_message and assistant_message else 0)
        )
        next_preview = preview or existing.last_message_preview
        next_vault = (
            vault_db_path
            if vault_db_path is not None
            else existing.vault_db_path
        )
        next_actor = (actor or existing.actor or "").strip() or existing.actor
        next_section = (sec or existing.section) if sec else existing.section
        next_last = lw or existing.last_worker_id
        created_at = existing.created_at or now
    else:
        auto_title = _title_from_first_message(user_message) or _title_from_first_message(
            assistant_message
        )
        if not auto_title:
            auto_title = f"Conversación {now[:10]}"
        explicit = (title or "").strip()
        if explicit and not _is_generic_conversation_title(explicit):
            next_title = explicit
            update_title_on_conflict = True
        elif _title_from_first_message(user_message):
            next_title = _title_from_first_message(user_message)
        else:
            next_title = explicit or auto_title
            update_title_on_conflict = bool(explicit)
        next_count = message_count if message_count is not None else (2 if user_message and assistant_message else 0)
        next_preview = preview
        next_vault = (vault_db_path or "").strip()
        next_actor = (actor or "").strip()
        next_section = sec
        next_last = lw
        created_at = now

    workers_json = json.dumps(worker_list, ensure_ascii=False)
    title_conflict_sql = (
        "excluded.title" if update_title_on_conflict else "main.admin_conversations.title"
    )
    try:
        sql = f"""
                INSERT INTO main.admin_conversations (
                    conversation_id, tenant_id, actor_email, title, worker_id, vault_path,
                    created_at, updated_at, section, last_worker_id, preferred_worker_id,
                    workers_json, last_message_preview, message_count, origin
                ) VALUES (
                    '{_sql_lit(sid, 128)}',
                    '{_sql_lit(tid, 128)}',
                    '{_sql_lit(next_actor, 256)}',
                    '{_sql_lit(next_title, 512)}',
                    '{_sql_lit(next_last or preferred, 128)}',
                    '{_sql_lit(next_vault or "", 1024)}',
                    '{_sql_lit(created_at, 64)}',
                    '{_sql_lit(now, 64)}',
                    '{_sql_lit(next_section, 64)}',
                    '{_sql_lit(next_last, 128)}',
                    '{_sql_lit(preferred, 128)}',
                    '{_sql_lit(workers_json, 4096)}',
                    '{_sql_lit(next_preview, 256)}',
                    {int(next_count)},
                    '{_sql_lit(origin or "admin_ui", 64)}'
                )
                ON CONFLICT (conversation_id) DO UPDATE SET
                    tenant_id = excluded.tenant_id,
                    actor_email = excluded.actor_email,
                    title = {title_conflict_sql},
                    worker_id = excluded.worker_id,
                    vault_path = excluded.vault_path,
                    updated_at = excluded.updated_at,
                    section = excluded.section,
                    last_worker_id = excluded.last_worker_id,
                    preferred_worker_id = excluded.preferred_worker_id,
                    workers_json = excluded.workers_json,
                    last_message_preview = excluded.last_message_preview,
                    message_count = excluded.message_count,
                    origin = excluded.origin
                """
        _execute_hub_write(sql)
        # db-writer is async: a hub read here returns the pre-enqueue row and the
        # PATCH API would echo the old title back into the editor.
        return _row_to_meta(
            {
                "conversation_id": sid,
                "tenant_id": tid,
                "actor_email": next_actor,
                "title": next_title,
                "worker_id": next_last or preferred,
                "vault_path": next_vault or "",
                "created_at": created_at,
                "updated_at": now,
                "section": next_section,
                "last_worker_id": next_last,
                "preferred_worker_id": preferred,
                "workers_json": workers_json,
                "last_message_preview": next_preview,
                "message_count": int(next_count),
                "origin": origin or "admin_ui",
            }
        )
    except FileNotFoundError:
        return None
    except Exception as exc:
        _log.warning("admin_conversations_db: upsert %s/%s: %s", tid, sid, exc)
        return None


def db_list_conversations(
    tenant_id: str,
    *,
    section: str | None = None,
    worker: str | None = None,
    actor: str | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    tid = (tenant_id or "default").strip() or "default"
    limit = max(1, min(int(limit), 200))
    offset = max(0, int(offset))
    try:
        with _open_db(read_only=True) as db:
            ensure_admin_conversation_columns(db)
            rows = _fetch_dicts(
                db,
                "SELECT * FROM main.admin_conversations "
                f"WHERE tenant_id = '{_sql_lit(tid, 128)}' "
                "ORDER BY updated_at DESC",
            )
    except FileNotFoundError:
        return [], 0
    except Exception as exc:
        _log.warning("admin_conversations_db: list %s: %s", tid, exc)
        return [], 0

    sec_f = (section or "").strip().lower()
    worker_f = (worker or "").strip()
    actor_f = (actor or "").strip().lower()
    q_f = (q or "").strip().lower()
    items = []
    for row in rows:
        meta = _row_to_meta(row)
        if sec_f and meta.section.lower() != sec_f:
            continue
        if worker_f:
            if meta.last_worker_id != worker_f and worker_f not in meta.workers:
                continue
        if actor_f and actor_f not in (meta.actor or "").lower():
            continue
        if q_f:
            blob = f"{meta.title} {meta.last_message_preview}".lower()
            if q_f not in blob:
                continue
        items.append(meta)
    total = len(items)
    return items[offset : offset + limit], total


def db_patch_conversation_title(tenant_id: str, session_id: str, title: str):
    meta = db_get_conversation_meta(tenant_id, session_id)
    if meta is None:
        return None
    return db_upsert_conversation_meta(
        tenant_id=meta.tenant_id,
        session_id=meta.session_id,
        actor=meta.actor,
        section=meta.section,
        last_worker_id=meta.last_worker_id,
        preferred_worker_id=meta.preferred_worker_id,
        workers=meta.workers,
        message_count=meta.message_count,
        title=(title or "").strip() or meta.title,
        vault_db_path=meta.vault_db_path,
        origin=meta.origin,
        assistant_message=meta.last_message_preview,
    )


def db_patch_conversation_vault(tenant_id: str, session_id: str, vault_db_path: str | None):
    meta = db_get_conversation_meta(tenant_id, session_id)
    if meta is None:
        return None
    return db_upsert_conversation_meta(
        tenant_id=meta.tenant_id,
        session_id=meta.session_id,
        actor=meta.actor,
        section=meta.section,
        last_worker_id=meta.last_worker_id,
        preferred_worker_id=meta.preferred_worker_id,
        workers=meta.workers,
        message_count=meta.message_count,
        title=meta.title,
        vault_db_path=(vault_db_path or "").strip(),
        origin=meta.origin,
        assistant_message=meta.last_message_preview,
    )


def db_patch_conversation_worker(tenant_id: str, session_id: str, worker_id: str | None):
    meta = db_get_conversation_meta(tenant_id, session_id)
    if meta is None:
        return None
    wid = (worker_id or "").strip()
    workers = list(meta.workers)
    if wid and wid not in workers:
        workers.append(wid)
    return db_upsert_conversation_meta(
        tenant_id=meta.tenant_id,
        session_id=meta.session_id,
        actor=meta.actor,
        section=meta.section,
        last_worker_id=wid or meta.last_worker_id,
        preferred_worker_id=wid,
        workers=workers,
        message_count=meta.message_count,
        title=meta.title,
        vault_db_path=meta.vault_db_path,
        origin=meta.origin,
        assistant_message=meta.last_message_preview,
    )


def db_delete_conversation(tenant_id: str, session_id: str) -> bool:
    tid = (tenant_id or "default").strip() or "default"
    sid = (session_id or "").strip()
    if not sid:
        return False
    try:
        _execute_hub_write(
            [
                "DELETE FROM main.admin_conversation_messages "
                f"WHERE conversation_id = '{_sql_lit(sid, 128)}'",
                "DELETE FROM main.admin_conversation_artifacts "
                f"WHERE conversation_id = '{_sql_lit(sid, 128)}'",
                "DELETE FROM main.admin_conversations "
                f"WHERE tenant_id = '{_sql_lit(tid, 128)}' "
                f"AND conversation_id = '{_sql_lit(sid, 128)}'",
            ]
        )
        return True
    except FileNotFoundError:
        return False
    except Exception as exc:
        _log.warning("admin_conversations_db: delete %s/%s: %s", tid, sid, exc)
        return False


def db_load_messages(tenant_id: str, session_id: str) -> list[dict[str, str]]:
    sid = (session_id or "").strip()
    if not sid:
        return []
    # Messages are keyed by conversation_id only (session_id); tenant checked via meta.
    try:
        with _open_db(read_only=True) as db:
            rows = _fetch_dicts(
                db,
                "SELECT role, content FROM main.admin_conversation_messages "
                f"WHERE conversation_id = '{_sql_lit(sid, 128)}' "
                "ORDER BY created_at ASC, message_id ASC",
            )
    except FileNotFoundError:
        return []
    except Exception as exc:
        _log.warning("admin_conversations_db: load messages %s: %s", sid, exc)
        return []
    out: list[dict[str, str]] = []
    for row in rows:
        role = str(row.get("role") or "").strip().lower()
        content = str(row.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content})
    return out


def db_save_messages(tenant_id: str, session_id: str, items: list[dict[str, str]]) -> None:
    """Replace conversation message history (same semantics as Redis SET)."""
    sid = (session_id or "").strip()
    if not sid:
        return
    tid = (tenant_id or "default").strip() or "default"
    rows: list[dict[str, str]] = []
    for item in items:
        role = str(item.get("role") or "").strip().lower()
        content = str(item.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            rows.append({"role": role, "content": content})
    if not rows:
        return
    try:
        now = _now_iso()
        statements = [
            "DELETE FROM main.admin_conversation_messages "
            f"WHERE conversation_id = '{_sql_lit(sid, 128)}'"
        ]
        for idx, item in enumerate(rows):
            mid = f"msg_{uuid.uuid4().hex}"
            stamp = now
            try:
                base = datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
                stamp = (base.replace(microsecond=min(idx, 999999))).strftime(
                    "%Y-%m-%dT%H:%M:%S.%fZ"
                )
            except Exception:
                stamp = now
            statements.append(
                "INSERT INTO main.admin_conversation_messages ("
                "message_id, conversation_id, role, content, artifact_json, created_at"
                ") VALUES ("
                f"'{_sql_lit(mid, 64)}', "
                f"'{_sql_lit(sid, 128)}', "
                f"'{_sql_lit(item['role'], 32)}', "
                f"'{_sql_lit(item['content'], 100000)}', "
                "'', "
                f"'{_sql_lit(stamp, 64)}')"
            )
        statements.append(
            "UPDATE main.admin_conversations SET "
            f"message_count = {len(rows)}, "
            f"updated_at = '{_sql_lit(now, 64)}' "
            f"WHERE conversation_id = '{_sql_lit(sid, 128)}' "
            f"AND tenant_id = '{_sql_lit(tid, 128)}'"
        )
        _execute_hub_write(statements)
    except FileNotFoundError:
        return
    except Exception as exc:
        _log.warning("admin_conversations_db: save messages %s: %s", sid, exc)
