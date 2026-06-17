"""Chat-scoped runtime state stored in the legacy ``agent_config`` table."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from duckclaw import db_write_queue
from duckclaw.write_commands import ForgetChatStateCommand, UpsertAgentConfigEntriesCommand

_PREFIX = "chat_"
_AGENT_CONFIG_TABLE = "agent_config"


def _skip_runtime_ddl(db: Any) -> bool:
    """Return True when runtime code must not create or alter DuckDB tables."""
    return bool(getattr(db, "_read_only", False))


def _chat_key(chat_id: Any, suffix: str) -> str:
    """Key for agent_config; supports numeric Telegram IDs and string API session IDs."""
    try:
        cid = int(chat_id)
        return f"{_PREFIX}{cid}_{suffix}"
    except (TypeError, ValueError):
        return f"{_PREFIX}{str(chat_id)[:64]}_{suffix}"


def _ensure_agent_config(db: Any) -> None:
    if _skip_runtime_ddl(db):
        return
    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_AGENT_CONFIG_TABLE} (
            key VARCHAR PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def get_chat_state(db: Any, chat_id: Any, key: str) -> str:
    """Read a chat-scoped config key from agent_config."""
    _ensure_agent_config(db)
    k = _chat_key(chat_id, key).replace("'", "''")[:200]
    try:
        result = db.query(f"SELECT value FROM {_AGENT_CONFIG_TABLE} WHERE key = '{k}' LIMIT 1")
        rows = json.loads(result) if isinstance(result, str) else (result or [])
        if rows and isinstance(rows[0], dict):
            return (rows[0].get("value") or "").strip()
    except Exception:
        pass
    return ""


def set_chat_state(db: Any, chat_id: Any, key: str, value: str) -> None:
    """Write a chat-scoped config key to agent_config."""
    _ensure_agent_config(db)
    k = _chat_key(chat_id, key).replace("'", "''")[:128]
    v = str(value).replace("'", "''")[:16384]
    db.execute(
        f"""
        INSERT INTO {_AGENT_CONFIG_TABLE} (key, value) VALUES ('{k}', '{v}')
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """
    )


def forget_chat_state(db: Any, chat_id: Any) -> None:
    """Delete legacy conversation rows and audited state for one chat/session."""
    if _skip_runtime_ddl(db):
        return
    try:
        cid = int(chat_id)
        db.execute(f"DELETE FROM telegram_conversation WHERE chat_id = {cid}")
    except (TypeError, ValueError):
        sid = str(chat_id).replace("'", "''")[:256]
        try:
            db.execute(f"DELETE FROM api_conversation WHERE session_id = '{sid}'")
        except Exception:
            pass
    try:
        _ensure_agent_config(db)
        key = _chat_key(chat_id, "last_audit").replace("'", "''")[:128]
        db.execute(f"DELETE FROM {_AGENT_CONFIG_TABLE} WHERE key = '{key}'")
    except Exception:
        pass


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


def set_chat_state_via_typed_command(
    db: Any,
    chat_id: Any,
    key: str,
    value: str,
    *,
    tenant_id: str = "default",
    actor_email: str = "",
) -> tuple[bool, str]:
    """Write chat-scoped agent_config directly or through the typed DB-writer queue."""
    if not _skip_runtime_ddl(db):
        set_chat_state(db, chat_id, key, value)
        return True, ""

    raw_path = str(getattr(db, "_path", "") or "").strip()
    if not raw_path or raw_path == ":memory:":
        return False, "Ruta de bóveda no resuelta"
    try:
        target_db_path = str(Path(raw_path).expanduser().resolve())
    except OSError:
        target_db_path = raw_path

    chat_actor = actor_email or f"chat:{str(chat_id or 'default').strip() or 'default'}"
    command = UpsertAgentConfigEntriesCommand(
        tenant_id=str(tenant_id or "default").strip() or "default",
        actor_email=chat_actor,
        entries={_chat_key(chat_id, key)[:128]: str(value)[:16384]},
    )

    released_ro, resume = _release_ro_handle_for_writer(db)
    try:
        task_id = db_write_queue.enqueue_typed_command(
            command,
            db_path=target_db_path,
            user_id=str(chat_id or "default").strip() or "default",
        )
        status = db_write_queue.poll_task_status_sync(task_id, timeout_sec=30.0)
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


def forget_chat_state_via_typed_command(
    db: Any,
    chat_id: Any,
    *,
    tenant_id: str = "default",
    actor_email: str = "",
) -> tuple[bool, str]:
    """Delete chat/session state directly or through the typed DB-writer queue."""
    if not _skip_runtime_ddl(db):
        forget_chat_state(db, chat_id)
        return True, ""

    raw_path = str(getattr(db, "_path", "") or "").strip()
    if not raw_path or raw_path == ":memory:":
        return False, "Ruta de bóveda no resuelta"
    try:
        target_db_path = str(Path(raw_path).expanduser().resolve())
    except OSError:
        target_db_path = raw_path

    chat_actor = actor_email or f"chat:{str(chat_id or 'default').strip() or 'default'}"
    command = ForgetChatStateCommand(
        tenant_id=str(tenant_id or "default").strip() or "default",
        actor_email=chat_actor,
        chat_id=str(chat_id or "default").strip() or "default",
    )

    released_ro, resume = _release_ro_handle_for_writer(db)
    try:
        task_id = db_write_queue.enqueue_typed_command(
            command,
            db_path=target_db_path,
            user_id=str(chat_id or "default").strip() or "default",
        )
        status = db_write_queue.poll_task_status_sync(task_id, timeout_sec=30.0)
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


def get_global_config(db: Any, key: str) -> str:
    """Read a global config key from agent_config."""
    _ensure_agent_config(db)
    k = str(key).replace("'", "''")[:128]
    try:
        result = db.query(f"SELECT value FROM {_AGENT_CONFIG_TABLE} WHERE key = '{k}' LIMIT 1")
        rows = json.loads(result) if isinstance(result, str) else (result or [])
        if rows and isinstance(rows[0], dict):
            return (rows[0].get("value") or "").strip()
    except Exception:
        pass
    return ""


def set_global_config(db: Any, key: str, value: str) -> None:
    """Write a global config key to agent_config."""
    _ensure_agent_config(db)
    k = str(key).replace("'", "''")[:128]
    v = str(value).replace("'", "''")[:16384]
    db.execute(
        f"""
        INSERT INTO {_AGENT_CONFIG_TABLE} (key, value) VALUES ('{k}', '{v}')
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """
    )


_get_global_config = get_global_config
_set_global_config = set_global_config


def execute_forget(db: Any, chat_id: Any, *, tenant_id: Any = None) -> str:
    """/forget: borra historial de la conversación y reinicia estado."""
    tid = str(tenant_id or "default").strip() or "default"
    ok, err = forget_chat_state_via_typed_command(db, chat_id, tenant_id=tid)
    if not ok:
        return f"No se pudo borrar historial: {err}"
    if os.environ.get("LANGCHAIN_TRACING_V2", "").lower() == "true":
        try:
            import langsmith

            # Log evento Habeas Data (opcional: run_id no disponible aquí)
            pass
        except Exception:
            pass
    return "✅ Historial borrado."


def execute_context_toggle(
    db: Any,
    chat_id: Any,
    on_off: str,
    *,
    tenant_id: Any = None,
) -> str:
    """/context on|off: activa o desactiva inyección de memoria a largo plazo."""
    tid = str(tenant_id or "default").strip() or "default"
    v = (on_off or "").strip().lower()
    if v in ("on", "1", "true", "sí", "si"):
        ok, err = set_chat_state_via_typed_command(
            db,
            chat_id,
            "use_rag",
            "true",
            tenant_id=tid,
        )
        if not ok:
            return f"No se pudo actualizar contexto largo: {err}"
        return "✅ Contexto largo activado (más mensajes en historial)."
    if v in ("off", "0", "false"):
        ok, err = set_chat_state_via_typed_command(
            db,
            chat_id,
            "use_rag",
            "false",
            tenant_id=tid,
        )
        if not ok:
            return f"No se pudo actualizar contexto largo: {err}"
        return "✅ Contexto largo desactivado (solo historial reciente)."
    current = get_chat_state(db, chat_id, "use_rag")
    return (
        "Uso: `/context on` | `/context off` | `/context --add` [texto o pie de foto en imagen/álbum] | "
        "`/context --summary` (`--summarize`)\n"
        f"Estado actual (historial largo): {'on' if current != 'false' else 'off'}."
    )

