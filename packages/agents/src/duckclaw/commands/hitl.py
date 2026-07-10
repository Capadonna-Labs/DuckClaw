"""DB-first HITL fly commands: approve/reject code and uncertainty resolution."""

from __future__ import annotations

import re
from typing import Any

from duckclaw.commands.chat_state import get_chat_state
from duckclaw.hitl.code_decision_service import approve_code_decision, reject_code_decision
from duckclaw.hitl.model_approval_service import approve_model_adapter
from duckclaw.hitl.loop_validation_service import approve_validation, reject_validation
from duckclaw.hitl.uncertainty_service import list_pending_uncertainty_events, resolve_uncertainty_event

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def execute_resolve_uncertainty(
    db: Any, chat_id: Any, args: str, *, tenant_id: Any = None
) -> str:
    """/resolve_uncertainty <event_uuid>: cierra PENDING_HITL en agent_uncertainty_log."""
    eid = (args or "").strip().lower().split()[0] if (args or "").strip() else ""
    if not _UUID_RE.match(eid):
        return "Uso: /resolve_uncertainty <event_id_UUID>"
    try:
        tid = str(tenant_id or get_chat_state(db, chat_id, "tenant_id") or "default").strip() or "default"
        uid = str(get_chat_state(db, chat_id, "last_requester_id") or tid).strip() or tid
        result = resolve_uncertainty_event(db, event_id=eid, tenant_id=tid, user_id=uid)
        if result.get("error"):
            return f"No: {result['error']}"
        return (
            f"Incertidumbre resuelta. event_id={result.get('event_id')} "
            f"session_uid={result.get('session_uid')}"
        )
    except Exception as exc:
        return f"Error al resolver incertidumbre: {exc}"


def execute_code_reject(db: Any, chat_id: Any, args: str) -> str:
    """/reject-code <uuid> [razón]: rechaza code_decision PENDING_HITL."""
    parts = (args or "").strip().split(maxsplit=1)
    decision_id = (parts[0] if parts else "").strip().lower()
    rationale = (parts[1] if len(parts) > 1 else "").strip()
    if not _UUID_RE.match(decision_id):
        return "Uso: /reject-code <decision_id_UUID> [razón]"
    tid = str(get_chat_state(db, chat_id, "tenant_id") or "default").strip() or "default"
    uid = str(get_chat_state(db, chat_id, "last_requester_id") or tid).strip() or tid
    result = reject_code_decision(
        db,
        decision_id=decision_id,
        tenant_id=tid,
        user_id=uid,
        rationale=rationale,
        chat_id=str(chat_id or "").strip(),
    )
    if result.get("error"):
        return f"No: {result['error']}"
    return f"Code decision {decision_id} → {result.get('status', 'REJECTED')}"


def execute_code_approve(db: Any, chat_id: Any, args: str) -> str:
    """/approve-code <uuid>: aprueba code_decision y abre PR vía GitHub MCP."""
    decision_id = (args or "").strip().lower().split()[0] if (args or "").strip() else ""
    if not _UUID_RE.match(decision_id):
        return "Uso: /approve-code <decision_id_UUID>"
    tid = str(get_chat_state(db, chat_id, "tenant_id") or "default").strip() or "default"
    uid = str(get_chat_state(db, chat_id, "last_requester_id") or tid).strip() or tid
    result = approve_code_decision(
        db,
        decision_id=decision_id,
        tenant_id=tid,
        user_id=uid,
        chat_id=str(chat_id or "").strip(),
    )
    if result.get("error"):
        return f"No: {result['error']}"
    pr_url = (result.get("pr_url") or "").strip()
    suffix = f" PR: {pr_url}" if pr_url else ""
    return f"Aprobado {decision_id}.{suffix}"


def execute_loop_approve(db: Any, chat_id: Any, args: str, *, tenant_id: Any = None) -> str:
    """/loop-approve [uuid]: confirma homeostasis tras validación HITL."""
    parts = (args or "").strip().split()
    validation_id = (parts[0] if parts else "").strip().lower() or None
    if validation_id and not _UUID_RE.match(validation_id):
        return "Uso: /loop-approve [validation_id_UUID]"
    tid = str(tenant_id or get_chat_state(db, chat_id, "tenant_id") or "default").strip() or "default"
    result = approve_validation(db, chat_id, validation_id, tenant_id=tid)
    if not result.get("ok"):
        err = str(result.get("error") or "error")
        if err == "no_pending_validation":
            return "No hay validación HITL de homeostasis pendiente en este chat."
        if err == "validation_id_mismatch":
            expected = result.get("expected") or ""
            return f"No coincide validation_id. Pendiente: `{expected}`"
        if err == "persist_failed":
            return f"No: {result.get('message') or err}"
        return f"No: {err}"
    try:
        from duckclaw.commands.loop import clear_loop_schedule

        clear_loop_schedule(db, chat_id, tenant_id=tid)
    except Exception:
        pass
    vid = result.get("validation_id") or ""
    return (
        f"✅ Homeostasis confirmada — modo `/loop` detenido. validation_id={vid}. "
        "Metas /goals confirmadas en equilibrio."
    )


def execute_loop_reject(db: Any, chat_id: Any, args: str, *, tenant_id: Any = None) -> str:
    """/loop-reject [uuid] [razón]: rechaza declaración de homeostasis."""
    parts = (args or "").strip().split(maxsplit=1)
    validation_id = None
    rationale = ""
    if parts:
        first = parts[0].strip().lower()
        if _UUID_RE.match(first):
            validation_id = first
            rationale = (parts[1] if len(parts) > 1 else "").strip()
        else:
            rationale = (args or "").strip()
    tid = str(tenant_id or get_chat_state(db, chat_id, "tenant_id") or "default").strip() or "default"
    result = reject_validation(
        db,
        chat_id,
        validation_id,
        rationale=rationale,
        tenant_id=tid,
    )
    if not result.get("ok"):
        err = str(result.get("error") or "error")
        if err == "no_pending_validation":
            return "No hay validación HITL de homeostasis pendiente en este chat."
        if err == "validation_id_mismatch":
            expected = result.get("expected") or ""
            return f"No coincide validation_id. Pendiente: `{expected}`"
        if err == "persist_failed":
            return f"No: {result.get('message') or err}"
        return f"No: {err}"
    vid = result.get("validation_id") or ""
    reason = (result.get("rationale") or "").strip()
    suffix = f" Razón: {reason}" if reason else ""
    return f"Homeostasis no confirmada (validation_id={vid}).{suffix}"


def execute_uncertainty_status(db: Any, chat_id: Any, args: str) -> str:
    """/uncertainty --status: lista eventos PENDING_HITL del vault activo."""
    _ = chat_id, args
    try:
        rows = list_pending_uncertainty_events(db, limit=10)
        if not rows:
            return "Sin eventos de incertidumbre PENDING_HITL en el vault activo."
        lines = ["**Incertidumbre pendiente (HITL)**"]
        for row in rows:
            lines.append(
                f"- `{row.get('id')}` · {row.get('trigger_context')} · C={row.get('confidence_score')}"
            )
        lines.append("\nResuelve con `/resolve_uncertainty <event_id>`.")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error listando incertidumbre: {exc}"


def execute_approve_model(db: Any, chat_id: Any, args: str) -> str:
    """/approve-model <adapter_path>: promueve adapter LoRA tras evaluación HITL."""
    _ = db
    adapter = (args or "").strip().split()[0] if (args or "").strip() else ""
    if not adapter:
        return "Uso: /approve-model <adapter_path>\nEj: /approve-model packages/agents/train/gemma4/adapters_lora_yaml"
    result = approve_model_adapter(adapter_path=adapter, chat_id=str(chat_id or "").strip())
    if not result.get("ok"):
        return f"No: {result.get('error', 'error desconocido')}"
    return str(result.get("message") or "Modelo aprobado.")


def execute_meditate_approve(db: Any, chat_id: Any, args: str, *, tenant_id: Any = None) -> str:
    return execute_loop_approve(db, chat_id, args, tenant_id=tenant_id)


def execute_meditate_reject(db: Any, chat_id: Any, args: str, *, tenant_id: Any = None) -> str:
    return execute_loop_reject(db, chat_id, args, tenant_id=tenant_id)
