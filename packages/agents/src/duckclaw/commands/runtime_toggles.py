"""Chat-scoped runtime toggles for sandbox execution and sandbox network."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from duckclaw.commands.team_templates import get_team_templates, get_tenant_team_templates
from duckclaw.forge.schema import resolve_sandbox_network_policy
from duckclaw.runtime_session_settings import (
    RUNTIME_SESSION_DOMAIN,
    resolve_session_runtime_setting,
    runtime_session_actor,
    upsert_session_runtime_setting,
)
from duckclaw.write_commands import UpsertRuntimeSettingCommand

SandboxSessionCleanup = Callable[[str], None]

_sandbox_session_cleanup: SandboxSessionCleanup | None = None
_log = logging.getLogger(__name__)


def configure_sandbox_session_cleanup(cleanup: SandboxSessionCleanup | None) -> None:
    """Inject graph-local sandbox session cleanup without importing graph modules."""
    global _sandbox_session_cleanup
    _sandbox_session_cleanup = cleanup


def _parse_toggle_bool(raw: str) -> bool | None:
    value = (raw or "").strip().lower()
    if value in ("on", "1", "true", "sí", "si"):
        return True
    if value in ("off", "0", "false"):
        return False
    return None


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


def _set_runtime_toggle_state(
    db: Any,
    chat_id: Any,
    key_suffix: str,
    value: str,
    *,
    tenant_id: str = "default",
) -> tuple[bool, str]:
    """Persist chat-scoped runtime toggle directly or through the typed DB-writer queue."""
    if not bool(getattr(db, "_read_only", False)):
        upsert_session_runtime_setting(
            db,
            chat_id,
            key_suffix,
            value,
            tenant_id=tenant_id,
            value_kind="boolean",
            updated_by="runtime-toggle",
        )
        return True, ""

    raw_path = str(getattr(db, "_path", "") or "").strip()
    if not raw_path or raw_path == ":memory:":
        return False, "Ruta de bóveda no resuelta"

    try:
        target_db_path = str(Path(raw_path).expanduser().resolve())
    except OSError:
        target_db_path = raw_path

    command = UpsertRuntimeSettingCommand(
        tenant_id=str(tenant_id or "default").strip() or "default",
        actor_email=runtime_session_actor(chat_id),
        domain=RUNTIME_SESSION_DOMAIN,
        key=key_suffix,
        value=str(value)[:8192],
        value_kind="boolean",
    )

    try:
        from duckclaw.db_write_queue import enqueue_typed_command, poll_task_status_sync
    except Exception as exc:
        return False, f"cola DuckDB no disponible: {exc}"

    released_ro, resume = _release_ro_handle_for_writer(db)
    try:
        task_id = enqueue_typed_command(
            command,
            db_path=target_db_path,
            user_id=str(chat_id or "default").strip() or "default",
        )
        status = poll_task_status_sync(task_id, timeout_sec=30.0)
        if status is None:
            return False, "timeout esperando db-writer"
        if status.status != "success":
            return False, (status.detail or "db-writer failed")[:500]
        return True, ""
    finally:
        if released_ro and callable(resume):
            try:
                resume()
            except Exception:
                pass


def _get_runtime_toggle_state(
    db: Any,
    chat_id: Any,
    key_suffix: str,
    *,
    tenant_id: str = "default",
) -> str:
    return resolve_session_runtime_setting(
        db,
        chat_id,
        key_suffix,
        tenant_id=tenant_id,
    )


def set_runtime_toggle_state(
    db: Any,
    chat_id: Any,
    key_suffix: str,
    value: str,
    *,
    tenant_id: str = "default",
) -> tuple[bool, str]:
    """Persist a chat-scoped runtime toggle through the DB-first owner."""
    return _set_runtime_toggle_state(
        db,
        chat_id,
        key_suffix,
        value,
        tenant_id=tenant_id,
    )


def _resolve_worker_id_for_network_toggle(
    db: Any,
    chat_id: Any,
    worker_id: str,
    tenant_id: str,
) -> str:
    wid = (worker_id or "").strip()
    if wid:
        return wid
    for team in (
        get_team_templates(db, chat_id),
        get_tenant_team_templates(db, tenant_id),
    ):
        if team:
            candidate = str(team[0] or "").strip()
            if candidate:
                return candidate
    return "default"


def _cleanup_sandbox_session(chat_id: Any) -> None:
    cleanup = _sandbox_session_cleanup
    if cleanup is None:
        return
    try:
        cleanup(str(chat_id))
    except Exception:
        pass


def execute_sandbox_toggle(
    db: Any,
    chat_id: Any,
    on_off: str,
    *,
    tenant_id: str = "default",
) -> str:
    """/sandbox on|off: habilita/deshabilita ejecución de código para este chat."""
    tid = str(tenant_id or "default").strip() or "default"
    parsed = _parse_toggle_bool(on_off)
    if parsed is True:
        ok, err = _set_runtime_toggle_state(
            db,
            chat_id,
            "sandbox_enabled",
            "true",
            tenant_id=tid,
        )
        if not ok:
            return f"No se pudo guardar: {err}"
        db_path = getattr(db, "_path", None) or getattr(db, "path", None) or "(unknown_db_path)"
        _log.warning(
            "[sandbox-toggle] db_path=%r chat_id=%r sandbox_enabled=%r",
            db_path,
            chat_id,
            "true",
        )
        return "Entendido. He habilitado mis capacidades de ejecución de código para esta sesión."
    if parsed is False:
        ok, err = _set_runtime_toggle_state(
            db,
            chat_id,
            "sandbox_enabled",
            "false",
            tenant_id=tid,
        )
        if not ok:
            return f"No se pudo guardar: {err}"
        db_path = getattr(db, "_path", None) or getattr(db, "path", None) or "(unknown_db_path)"
        _log.warning(
            "[sandbox-toggle] db_path=%r chat_id=%r sandbox_enabled=%r",
            db_path,
            chat_id,
            "false",
        )
        return "Entendido. He desactivado mis capacidades de ejecución de código para esta sesión."

    current = _parse_toggle_bool(
        _get_runtime_toggle_state(db, chat_id, "sandbox_enabled", tenant_id=tid)
    )
    status = "habilitado" if current is True else "desactivado"
    return f"Uso: /sandbox on|off\nEstado actual: {status}."


def execute_internet_toggle(
    db: Any,
    chat_id: Any,
    on_off: str,
    *,
    worker_id: str = "",
    tenant_id: str = "default",
) -> str:
    """/internet on|off: red del sandbox por chat, limitada por la policy del worker."""
    tid = str(tenant_id or "default").strip() or "default"
    wid = _resolve_worker_id_for_network_toggle(db, chat_id, worker_id, tid)

    _, meta = resolve_sandbox_network_policy(
        wid,
        _get_runtime_toggle_state(
            db,
            chat_id,
            "sandbox_network_enabled",
            tenant_id=tid,
        ),
    )
    if not meta.get("toggle_available"):
        return (
            f"Este worker («{wid}») tiene red sandbox denegada en security_policy.yaml. "
            "No se puede activar internet desde el chat. Usa tavily_search o un worker con browser_sandbox "
            "habilitado por capability/policy."
        )

    parsed = _parse_toggle_bool(on_off)
    if parsed is True:
        ok, err = _set_runtime_toggle_state(
            db, chat_id, "sandbox_network_enabled", "true", tenant_id=tid
        )
        if not ok:
            return f"No se pudo guardar: {err}"
        _cleanup_sandbox_session(chat_id)
        return (
            "Internet en sandbox activado para esta sesión. "
            "El próximo run_sandbox/run_browser_sandbox usará red bridge."
        )
    if parsed is False:
        ok, err = _set_runtime_toggle_state(
            db, chat_id, "sandbox_network_enabled", "false", tenant_id=tid
        )
        if not ok:
            return f"No se pudo guardar: {err}"
        _cleanup_sandbox_session(chat_id)
        return "Internet en sandbox desactivado (network_mode=none) para esta sesión."

    effective = meta.get("effective") or "deny"
    return f"Uso: /internet on|off\nRed sandbox efectiva: {effective} (worker {wid})."
