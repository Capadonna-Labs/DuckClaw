"""Task history command and task_audit_log append helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, Optional, cast

from duckclaw.commands.chat_state import _skip_runtime_ddl, get_chat_state
from duckclaw.write_commands import AppendTaskAuditCommand


_TASK_AUDIT_TABLE = "task_audit_log"
_TASK_AUDIT_STATUSES = {
    "SUCCESS",
    "FAILED",
    "PROACTIVE_MESSAGE_SENT",
    "SECURITY_VIOLATION_ATTEMPT",
}
_TaskAuditStatus = Literal["SUCCESS", "FAILED", "PROACTIVE_MESSAGE_SENT", "SECURITY_VIOLATION_ATTEMPT"]


def get_history_limit_for_chat(db: Any, chat_id: Any, default: int = 10) -> int:
    """Return the chat history limit for graph invocation."""
    use_rag = get_chat_state(db, chat_id, "use_rag")
    if use_rag == "false":
        return 3
    return default


def _ensure_task_audit_log(db: Any) -> None:
    """Ensure task_audit_log exists when the caller owns a write-capable handle."""
    if _skip_runtime_ddl(db):
        return
    from duckclaw.write_command_handlers import _ensure_task_audit_log_table

    _ensure_task_audit_log_table(db)


def _infer_user_id_for_audit_queue(db_path: str) -> str:
    """Infer the private vault owner slug from a DuckDB path."""
    parts = Path(db_path).expanduser().resolve().parts
    if "private" in parts:
        i = parts.index("private")
        if i + 1 < len(parts):
            return str(parts[i + 1])
    return "default"


def _normalize_task_audit_status(status: str) -> str:
    normalized = (status or "SUCCESS").upper().strip()
    return normalized if normalized in _TASK_AUDIT_STATUSES else "SUCCESS"


def _release_ro_handle_for_writer(db: Any) -> tuple[bool, Any]:
    release = getattr(db, "release_file_handle_for_external_writer", None)
    suspend = getattr(db, "suspend_readonly_file_handle", None)
    resume = getattr(db, "resume_readonly_file_handle", None)
    if callable(release):
        release()
        return bool(callable(resume)), resume
    if callable(suspend) and callable(resume):
        suspend()
        return True, resume
    return False, resume


def _enqueue_task_audit_command(db: Any, command: AppendTaskAuditCommand) -> None:
    from duckclaw.db_write_fire_and_forget import (
        enqueue_write_and_resolve,
        write_poll_timeout_sec,
    )

    raw_path = str(getattr(db, "_path", "") or "").strip()
    if not raw_path or raw_path == ":memory:":
        return
    resolved = str(Path(raw_path).expanduser().resolve())
    user_id = _infer_user_id_for_audit_queue(resolved)
    released_ro, resume = _release_ro_handle_for_writer(db)
    try:
        ok, err = enqueue_write_and_resolve(
            command,
            db_path=resolved,
            user_id=user_id,
        )
        if not ok and write_poll_timeout_sec() > 0:
            raise RuntimeError(err or "task audit write failed")
    finally:
        if released_ro and callable(resume):
            try:
                resume()
            except Exception:
                pass


def append_task_audit(
    db: Any,
    tenant_id: Any,
    worker_id: str,
    query_prefix: str,
    status: str,
    duration_ms: int,
    plan_title: Optional[str] = None,
) -> None:
    """Append one task to task_audit_log for /history."""
    command = AppendTaskAuditCommand(
        tenant_id=str(tenant_id or "default").strip()[:128] or "default",
        actor_email="system",
        worker_id=(worker_id or "")[:64],
        query_prefix=(query_prefix or "")[:256],
        status=cast(_TaskAuditStatus, _normalize_task_audit_status(status)),
        duration_ms=max(0, int(duration_ms or 0)),
        plan_title=(plan_title or "")[:256],
    )
    if _skip_runtime_ddl(db):
        try:
            _enqueue_task_audit_command(db, command)
        except Exception:
            pass
        return
    from duckclaw.write_command_handlers import dispatch_command

    dispatch_command(db, command.model_dump())


def _is_simple_greeting(prefix: str) -> bool:
    """True when a short user message is just a greeting."""
    p = (prefix or "").strip().lower()[:50]
    if len(p) > 35:
        return False
    greetings = (
        "hola",
        "hi",
        "hey",
        "hello",
        "buenas",
        "qué tal",
        "que tal",
        "buenos días",
        "buenos dias",
        "buenas tardes",
        "buenas noches",
        "ola",
        "saludos",
        "ciao",
        "adios",
        "chao",
    )
    return p in greetings or p.rstrip("!?.") in greetings


def _is_complex_task(row: dict) -> bool:
    """True when the row represents a real task rather than a short greeting."""
    prefix = (row.get("query_prefix") or "").strip()
    if _is_simple_greeting(prefix):
        return False
    try:
        dur_ms = int(row.get("duration_ms") or 0)
    except (TypeError, ValueError):
        dur_ms = 0
    return dur_ms >= 1500 or len(prefix) > 20


def _history_rows(db: Any, tenant_s: str) -> list[dict[str, Any]]:
    r = db.query(
        f"""
        SELECT task_id, query_prefix, status, duration_ms, created_at, worker_id, plan_title
        FROM {_TASK_AUDIT_TABLE}
        WHERE tenant_id = '{tenant_s}'
        ORDER BY created_at DESC
        LIMIT 100
        """
    )
    rows = json.loads(r) if isinstance(r, str) else (r or [])
    return [row for row in rows if isinstance(row, dict)]


def _filtered_history_rows(rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    complex_rows = []
    one_greeting = None
    for row in rows:
        plan_title_raw = (row.get("plan_title") or "").strip()
        if _is_complex_task(row) and plan_title_raw:
            complex_rows.append(row)
        elif one_greeting is None and _is_simple_greeting(row.get("query_prefix") or ""):
            one_greeting = row
    filtered = complex_rows[:limit]
    if one_greeting is not None and len(filtered) < limit:
        filtered.append(one_greeting)
    return filtered


def _dedupe_history_rows(filtered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped = []
    for idx, row in enumerate(filtered):
        raw_plan = (row.get("plan_title") or "").strip()
        if not raw_plan:
            wid = (row.get("worker_id") or "").strip()
            status = (row.get("status") or "UNKNOWN").upper()
            try:
                dur_ms = int(row.get("duration_ms") or 0)
            except (TypeError, ValueError):
                dur_ms = 0
            has_better = False
            for j, other in enumerate(filtered):
                if j == idx:
                    continue
                other_plan = (other.get("plan_title") or "").strip()
                if not other_plan:
                    continue
                wid2 = (other.get("worker_id") or "").strip()
                status2 = (other.get("status") or "UNKNOWN").upper()
                try:
                    dur2 = int(other.get("duration_ms") or 0)
                except (TypeError, ValueError):
                    dur2 = 0
                if wid2 == wid and status2 == status and dur2 == dur_ms:
                    has_better = True
                    break
            if has_better:
                continue
        deduped.append(row)
    return deduped


def _row_duration_ms(row: dict[str, Any]) -> int:
    try:
        return int(row.get("duration_ms") or 0)
    except (TypeError, ValueError):
        return 0


def _format_history_lines(deduped: list[dict[str, Any]]) -> list[str]:
    lines = [f"📋 Últimas {len(deduped)}"]
    for i, row in enumerate(deduped, 1):
        prefix = (row.get("query_prefix") or "").strip()[:80]
        plan_title = (row.get("plan_title") or "").strip()
        if not plan_title:
            if prefix:
                words = prefix.split()
                plan_title = " ".join(words[:5])
            else:
                plan_title = "Interacción del Usuario"
        wid = (row.get("worker_id") or "").strip()
        dur_s = f"{_row_duration_ms(row) / 1000:.1f}s"
        worker_part = f"[{wid}] " if wid else ""
        lines.append(f"{i}. {worker_part}{plan_title} · ⏱️ {dur_s}")
    return lines


def _failed_24h_count(db: Any, tenant_s: str) -> Any:
    try:
        r24 = db.query(
            f"""
            SELECT COUNT(*) as cnt FROM {_TASK_AUDIT_TABLE}
            WHERE tenant_id = '{tenant_s}' AND status = 'FAILED'
            AND created_at > CURRENT_TIMESTAMP - INTERVAL '24 hours'
            """
        )
        rows24 = json.loads(r24) if isinstance(r24, str) else (r24 or [])
        return rows24[0].get("cnt", 0) if rows24 else 0
    except Exception:
        return 0


def execute_history(db: Any, chat_id: Any, args: str) -> str:
    """/history [n]: show complex task history backed by task_audit_log."""
    tenant_s = str(chat_id).replace("'", "''")[:128]
    try:
        n = int((args or "5").strip())
        n = max(1, min(n, 20))
    except ValueError:
        n = 5
    _ensure_task_audit_log(db)
    try:
        rows = _history_rows(db, tenant_s)
    except Exception as exc:
        return f"Error al cargar historial: {exc}."

    if not rows:
        return "📋 Sin tareas registradas."

    filtered = _filtered_history_rows(rows, n)
    if not filtered:
        return "📋 Sin tareas complejas."

    deduped = _dedupe_history_rows(filtered)
    if not deduped:
        return "📋 Sin tareas complejas."

    lines = _format_history_lines(deduped)
    success_rows = [r for r in filtered if (r.get("status") or "").upper() == "SUCCESS"]
    avg_ms = sum(_row_duration_ms(r) for r in success_rows) / len(success_rows) if success_rows else 0
    lines.append(f"— avg {avg_ms/1000:.1f}s · fallidas 24h: {_failed_24h_count(db, tenant_s)}")
    return "\n".join(lines)
