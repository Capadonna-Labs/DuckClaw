"""HITL validation for /loop homeostasis (chat_state pending, no DuckDB table)."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from duckclaw.commands.loop_state_keys import (
    LOOP_HITL_PENDING_KEY,
    get_loop_chat_state,
    persist_loop_chat_state,
)

_STATUS_PENDING = "PENDING_HITL"
_STATUS_APPROVED = "APPROVED"
_STATUS_REJECTED = "REJECTED"


def _parse_pending(raw: str) -> dict[str, Any] | None:
    text = (raw or "").strip()
    if not text:
        return None
    try:
        data = json.loads(text)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def get_pending_validation(db: Any, chat_id: Any) -> dict[str, Any] | None:
    """Return active PENDING_HITL snapshot for chat, or None."""
    data = _parse_pending(get_loop_chat_state(db, chat_id, LOOP_HITL_PENDING_KEY))
    if not data:
        return None
    if str(data.get("status") or "").upper() != _STATUS_PENDING:
        return None
    return data


def clear_pending_validation(
    db: Any,
    chat_id: Any,
    *,
    tenant_id: str = "default",
) -> tuple[bool, str]:
    return persist_loop_chat_state(
        db,
        chat_id,
        LOOP_HITL_PENDING_KEY,
        "",
        tenant_id=tenant_id,
    )


def _save_pending(
    db: Any,
    chat_id: Any,
    payload: dict[str, Any],
    *,
    tenant_id: str,
) -> tuple[bool, str]:
    return persist_loop_chat_state(
        db,
        chat_id,
        LOOP_HITL_PENDING_KEY,
        json.dumps(payload, ensure_ascii=False),
        tenant_id=tenant_id,
    )


def create_pending_validation(
    db: Any,
    chat_id: Any,
    *,
    tenant_id: str,
    snapshot: dict[str, Any],
    goals_summary: str = "",
) -> dict[str, Any]:
    """Create PENDING_HITL validation; error if one already active."""
    existing = get_pending_validation(db, chat_id)
    if existing:
        return {
            "ok": False,
            "error": "pending_validation_exists",
            "validation_id": existing.get("validation_id"),
            "status": existing.get("status"),
        }
    validation_id = str(uuid.uuid4())
    tid = str(tenant_id or "default").strip() or "default"
    payload: dict[str, Any] = {
        "validation_id": validation_id,
        "tenant_id": tid,
        "status": _STATUS_PENDING,
        "created_at": int(time.time()),
        "goals_summary": (goals_summary or "").strip(),
        "snapshot": snapshot if isinstance(snapshot, dict) else {},
    }
    ok, err = _save_pending(db, chat_id, payload, tenant_id=tid)
    if not ok:
        return {
            "ok": False,
            "error": "persist_failed",
            "message": err or "No se pudo guardar loop_hitl_pending",
        }
    return {
        "ok": True,
        "validation_id": validation_id,
        "status": _STATUS_PENDING,
        "payload": payload,
    }


def _match_validation_id(pending: dict[str, Any], validation_id: str | None) -> bool:
    vid = (validation_id or "").strip().lower()
    if not vid:
        return True
    return str(pending.get("validation_id") or "").strip().lower() == vid


def approve_validation(
    db: Any,
    chat_id: Any,
    validation_id: str | None = None,
    *,
    tenant_id: str = "default",
) -> dict[str, Any]:
    """Approve pending validation and clear chat state."""
    pending = get_pending_validation(db, chat_id)
    if not pending:
        return {"ok": False, "error": "no_pending_validation"}
    if not _match_validation_id(pending, validation_id):
        return {
            "ok": False,
            "error": "validation_id_mismatch",
            "expected": pending.get("validation_id"),
        }
    vid = str(pending.get("validation_id") or "")
    tid = str(tenant_id or pending.get("tenant_id") or "default").strip() or "default"
    ok, err = clear_pending_validation(db, chat_id, tenant_id=tid)
    if not ok:
        return {"ok": False, "error": "persist_failed", "message": err}
    return {
        "ok": True,
        "validation_id": vid,
        "status": _STATUS_APPROVED,
        "goals_summary": pending.get("goals_summary") or "",
    }


def reject_validation(
    db: Any,
    chat_id: Any,
    validation_id: str | None = None,
    *,
    rationale: str = "",
    tenant_id: str = "default",
) -> dict[str, Any]:
    """Reject pending validation and clear chat state."""
    pending = get_pending_validation(db, chat_id)
    if not pending:
        return {"ok": False, "error": "no_pending_validation"}
    if not _match_validation_id(pending, validation_id):
        return {
            "ok": False,
            "error": "validation_id_mismatch",
            "expected": pending.get("validation_id"),
        }
    vid = str(pending.get("validation_id") or "")
    tid = str(tenant_id or pending.get("tenant_id") or "default").strip() or "default"
    ok, err = clear_pending_validation(db, chat_id, tenant_id=tid)
    if not ok:
        return {"ok": False, "error": "persist_failed", "message": err}
    return {
        "ok": True,
        "validation_id": vid,
        "status": _STATUS_REJECTED,
        "rationale": (rationale or "").strip(),
        "goals_summary": pending.get("goals_summary") or "",
    }


def format_hitl_user_prompt(validation_id: str, goals_summary: str) -> str:
    """Human-readable prompt for chat after request_homeostasis_validation."""
    summary = (goals_summary or "").strip() or "(revisa /goals)"
    return (
        f"**Validación HITL homeostasis** — ¿Confirmas que las metas están cumplidas?\n\n"
        f"{summary}\n\n"
        f"validation_id: `{validation_id}`\n"
        f"- `/loop-approve {validation_id}` — confirmar homeostasis\n"
        f"- `/loop-reject {validation_id} <razón>` — rechazar"
    )
