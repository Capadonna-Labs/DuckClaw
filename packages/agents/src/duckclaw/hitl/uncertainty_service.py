"""Transversal HITL service for ``main.agent_uncertainty_log`` events."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from duckclaw.hitl.db_access import _query_rows, table_exists
from duckclaw.write_commands import ResolveUncertaintyEventCommand

_log = logging.getLogger(__name__)

_UNCERTAINTY_TABLE = "agent_uncertainty_log"


def _infer_user_id_for_queue(db_path: str) -> str:
    parts = Path(db_path).expanduser().resolve().parts
    if "private" in parts:
        idx = parts.index("private")
        if idx + 1 < len(parts):
            return str(parts[idx + 1])
    return "default"


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


def _enqueue_resolve(db: Any, command: ResolveUncertaintyEventCommand) -> None:
    from duckclaw.db_write_queue import enqueue_typed_command, poll_task_status_sync

    raw_path = str(getattr(db, "_path", "") or "").strip()
    if not raw_path or raw_path == ":memory:":
        raise RuntimeError("vault db path required for uncertainty mutation")
    resolved = str(Path(raw_path).expanduser().resolve())
    user_id = _infer_user_id_for_queue(resolved)
    released_ro, resume = _release_ro_handle_for_writer(db)
    try:
        task_id = enqueue_typed_command(command, db_path=resolved, user_id=user_id)
        status = poll_task_status_sync(task_id, timeout_sec=20.0)
        if status is not None and status.status == "failed":
            raise RuntimeError(status.detail or "uncertainty resolve failed")
    finally:
        if released_ro and callable(resume):
            try:
                resume()
            except Exception:
                pass


def _apply_resolve_rw(db: Any, command: ResolveUncertaintyEventCommand) -> None:
    from duckclaw.write_command_handlers import dispatch_command

    dispatch_command(db, command.model_dump())


def list_pending_uncertainty_events(db: Any, *, limit: int = 10) -> list[dict[str, Any]]:
    if not table_exists(db, _UNCERTAINTY_TABLE):
        return []
    bounded = max(1, min(int(limit or 10), 100))
    return _query_rows(
        db,
        """
        SELECT id, session_uid, worker_id, trigger_context, confidence_score,
               description, proposed_questions, status, created_at
        FROM main.agent_uncertainty_log
        WHERE status = 'PENDING_HITL'
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (bounded,),
    )


def resolve_uncertainty_event(
    db: Any,
    *,
    event_id: str,
    tenant_id: str,
    user_id: str,
) -> dict[str, Any]:
    eid = (event_id or "").strip()
    if not eid:
        return {"error": "event_id required"}

    if not table_exists(db, _UNCERTAINTY_TABLE):
        return {"error": "tabla agent_uncertainty_log no disponible en este vault"}

    rows = _query_rows(
        db,
        """
        SELECT id, session_uid, status
        FROM main.agent_uncertainty_log
        WHERE id = ?
        LIMIT 1
        """,
        (eid,),
    )
    if not rows:
        return {"error": f"event_id {eid} no encontrado"}
    row = rows[0]
    if str(row.get("status") or "").upper() != "PENDING_HITL":
        return {"error": f"status inválido para resolver: {row.get('status')}"}

    command = ResolveUncertaintyEventCommand(
        tenant_id=tenant_id or "default",
        actor_email=user_id or "system",
        event_id=eid,
        session_uid=str(row.get("session_uid") or ""),
        resolved_by=user_id or tenant_id or "system",
    )
    try:
        if bool(getattr(db, "_read_only", False)):
            _enqueue_resolve(db, command)
        else:
            _apply_resolve_rw(db, command)
    except Exception as exc:
        _log.exception("resolve uncertainty failed")
        return {"error": str(exc)}

    return {
        "event_id": eid,
        "session_uid": row.get("session_uid"),
        "status": "RESOLVED",
    }
