"""Dispatcher core de comandos on-the-fly (parse + route + handle)."""

from __future__ import annotations

from typing import Any, Optional, Tuple

from duckclaw.commands.audit import execute_audit
from duckclaw.commands.chat_state import (
    execute_context_toggle,
    execute_forget,
    get_chat_state,
    set_chat_state,
)
from duckclaw.commands.context_summarize import execute_summarize
from duckclaw.commands.comfyui import execute_comfyui_provider
from duckclaw.commands.crons import execute_crons_schedule
from duckclaw.commands.fly_misc import (
    execute_approve_reject,
    execute_help,
    execute_lake_status,
    execute_tasks,
)
from duckclaw.commands.goals import execute_homeostasis_goals
from duckclaw.commands.health import execute_health, execute_heartbeat
from duckclaw.commands.history import execute_history
from duckclaw.commands.hitl import (
    execute_approve_model,
    execute_code_approve,
    execute_code_reject,
    execute_loop_approve,
    execute_loop_reject,
    execute_meditate_approve,
    execute_meditate_reject,
    execute_resolve_uncertainty,
    execute_uncertainty_status,
)
from duckclaw.commands.loop import execute_loop, execute_loop_immediate, execute_loop_status
from duckclaw.commands.model_setup import _execute_setup, execute_model, execute_models, execute_prompt
from duckclaw.commands.runtime_toggles import execute_internet_toggle, execute_sandbox_toggle
from duckclaw.commands.sensors import execute_sensors
from duckclaw.commands.team_access import execute_team_whitelist
from duckclaw.commands.team_templates import _resolve_template_id, execute_team
from duckclaw.commands.vaults import execute_vault
from duckclaw.commands.workers import _DEFAULT_WORKER, execute_roles, execute_skills_list
from duckclaw.extensions.fly import dispatch_extension_fly_command
from duckclaw.utils.logger import format_chat_log_identity, get_obs_logger, log_fly, structured_log_context


def parse_command(text: str) -> Tuple[str, str]:
    """Parse /command or /command args. Returns (name, args)."""
    if not text or not text.strip().startswith("/"):
        return "", ""
    parts = text.strip().split(maxsplit=1)
    name = (parts[0] or "").lstrip("/").lower()
    if "@" in name:
        name = name.split("@", 1)[0]
    args = (parts[1] if len(parts) > 1 else "").strip()
    return name, args


def _fly_reply_preview(s: str, max_len: int = 120) -> str:
    """Resumen de respuesta para [FLY] sin volcar secretos ni bloques enormes."""
    t = (s or "").replace("\n", " ").strip()
    if len(t) > max_len:
        return t[:max_len] + "..."
    return t


def get_worker_id_for_chat(db: Any, chat_id: Any) -> str:
    """Devuelve el worker_id asignado a este chat. Por defecto: manager (orquesta y delega a templates)."""
    return get_chat_state(db, chat_id, "worker_id") or _DEFAULT_WORKER


def _dispatch_fly_command(
    db: Any,
    chat_id: Any,
    name: str,
    args: str,
    *,
    requester_id: Any = None,
    tenant_id: Any = None,
    vault_user_id: Any = None,
    username: str = "",
    entry_worker_id: str | None = None,
) -> Optional[str]:
    """Ejecuta un comando fly ya parseado (sin contexto de logging)."""
    if name == "sensors":
        return execute_sensors(db)
    if name == "lake":
        sub = (args or "").strip().lower()
        if sub in ("", "status"):
            return execute_lake_status()
        return "Uso: /lake o /lake status"
    if name in ("resolve_uncertainty", "resolve-uncertainty"):
        return execute_resolve_uncertainty(db, chat_id, args, tenant_id=tenant_id)
    if name == "uncertainty":
        sub = (args or "").strip().lower()
        if sub in ("--status", "status", ""):
            return execute_uncertainty_status(db, chat_id, args)
        return "Uso: /uncertainty --status"
    if name in ("approve_code", "approve-code", "reject_code", "reject-code"):
        ext_out = dispatch_extension_fly_command(
            name,
            db,
            chat_id,
            args,
            requester_id=requester_id,
            tenant_id=tenant_id,
            vault_user_id=vault_user_id,
            username=username,
            entry_worker_id=entry_worker_id,
        )
        if ext_out is not None:
            return ext_out
    if name in ("approve_code", "approve-code"):
        return execute_code_approve(db, chat_id, args)
    if name in ("reject_code", "reject-code"):
        return execute_code_reject(db, chat_id, args)
    if name in ("loop_approve", "loop-approve"):
        return execute_loop_approve(db, chat_id, args, tenant_id=tenant_id)
    if name in ("loop_reject", "loop-reject"):
        return execute_loop_reject(db, chat_id, args, tenant_id=tenant_id)
    if name in ("meditate_approve", "meditate-approve"):
        return execute_loop_approve(db, chat_id, args, tenant_id=tenant_id)
    if name in ("meditate_reject", "meditate-reject"):
        return execute_loop_reject(db, chat_id, args, tenant_id=tenant_id)
    if name in ("approve_model", "approve-model"):
        return execute_approve_model(db, chat_id, args)
    if name == "help":
        return execute_help(db, chat_id)
    if name == "role":
        return (
            "El comando /role ya no existe. Usa /workers para ver o definir el equipo, /help para ver todos los comandos."
        )
    if name == "roles":
        return execute_roles(db, chat_id, tenant_id=tenant_id)
    if name == "team":
        return execute_team_whitelist(db, tenant_id, requester_id, args)
    if name == "vault":
        return execute_vault(
            args,
            vault_user_id=vault_user_id or requester_id or chat_id,
            tenant_id=tenant_id,
            db=db,
            entry_worker_id=entry_worker_id,
            chat_id=chat_id,
            worker_id_resolver=get_worker_id_for_chat,
        )
    if name == "workers":
        return execute_team(
            db, chat_id, args, tenant_id=tenant_id, requester_id=requester_id
        )
    if name == "skills":
        return execute_skills_list(db, chat_id, args, tenant_id=tenant_id)
    if name == "forget":
        return execute_forget(db, chat_id, tenant_id=tenant_id)
    if name == "context":
        return execute_context_toggle(db, chat_id, args, tenant_id=tenant_id)
    if name == "summarize":
        resolved_wid = (entry_worker_id or "").strip() or get_worker_id_for_chat(db, chat_id)
        return execute_summarize(
            db,
            chat_id,
            args,
            tenant_id=tenant_id,
            vault_db_path=str(getattr(db, "_path", "") or "").strip() or None,
            worker_id=resolved_wid,
        )
    if name == "comfyui":
        return execute_comfyui_provider(db, chat_id, args, tenant_id=tenant_id)
    if name in ("sandbox", "sandox"):
        return execute_sandbox_toggle(db, chat_id, args, tenant_id=tenant_id)
    if name in ("internet", "red", "network"):
        return execute_internet_toggle(
            db,
            chat_id,
            args,
            worker_id=entry_worker_id or "",
            tenant_id=tenant_id,
        )
    if name == "heartbeat":
        return execute_heartbeat(db, chat_id, args, tenant_id=tenant_id)
    if name == "audit":
        return execute_audit(db, chat_id)
    if name == "health":
        return execute_health(db)
    if name == "approve":
        return execute_approve_reject(db, chat_id, True)
    if name == "reject":
        return execute_approve_reject(db, chat_id, False)
    if name in ("prompt", "system_prompt", "system"):
        return execute_prompt(db, chat_id, args)
    if name in ("model", "provider", "llm"):
        return execute_model(db, chat_id, args)
    if name in ("models",):
        return execute_models(db, chat_id, args)
    if name == "setup":
        return _execute_setup(db, chat_id, args)
    if name == "goals":
        return execute_homeostasis_goals(
            db,
            chat_id,
            args,
            tenant_id=tenant_id,
            vault_user_id=vault_user_id,
        )
    if name == "crons":
        return execute_crons_schedule(
            db,
            chat_id,
            args,
            tenant_id=tenant_id,
            vault_user_id=vault_user_id,
        )
    if name == "loop":
        args_norm = (args or "").strip().lower()
        first = args_norm.split()[0] if args_norm else ""
        loop_kwargs = dict(
            tenant_id=tenant_id,
            vault_user_id=vault_user_id,
            entry_worker_id=entry_worker_id,
        )
        if first == "--status":
            return execute_loop_status(
                db,
                chat_id,
                args,
                tenant_id=tenant_id,
                entry_worker_id=entry_worker_id,
            )
        if first in ("--self", "--now") or not args_norm:
            return execute_loop_immediate(db, chat_id, **loop_kwargs)
        if first in ("on", "off") or first == "--delta":
            return execute_loop(db, chat_id, args, **loop_kwargs)
        return execute_loop_immediate(db, chat_id, **loop_kwargs)
    if name == "meditate":
        return _dispatch_fly_command(
            db, chat_id, "loop", args,
            requester_id=requester_id, tenant_id=tenant_id,
            vault_user_id=vault_user_id, username=username,
            entry_worker_id=entry_worker_id,
        )
    if name == "tasks":
        return execute_tasks(db, chat_id)
    if name == "history":
        return execute_history(db, chat_id, args)
    ext_out = dispatch_extension_fly_command(
        name,
        db,
        chat_id,
        args,
        requester_id=requester_id,
        tenant_id=tenant_id,
        vault_user_id=vault_user_id,
        username=username,
        entry_worker_id=entry_worker_id,
    )
    if ext_out is not None:
        return ext_out
    return None


def handle_command(
    db: Any,
    chat_id: Any,
    text: str,
    *,
    requester_id: Any = None,
    tenant_id: Any = None,
    vault_user_id: Any = None,
    username: str = "",
    entry_worker_id: str | None = None,
) -> Optional[str]:
    """
    Middleware: si el mensaje es un comando on-the-fly, ejecuta y retorna la respuesta.
    Si no es comando o no es manejado, retorna None.
    """
    name, args = parse_command(text)
    if not name:
        return None
    tid = str(tenant_id or "default").strip() or "default"
    try:
        cid = str(chat_id if chat_id is not None else "unknown").strip() or "unknown"
    except Exception:
        cid = "unknown"
    uname = (username or "").strip()
    if not uname and db is not None:
        try:
            uname = str(get_chat_state(db, chat_id, "username") or "").strip()
        except Exception:
            uname = ""
    chat_ident = format_chat_log_identity(cid, uname or None)
    _fly_log = get_obs_logger("duckclaw.fly")
    with structured_log_context(tenant_id=tid, worker_id="gateway", chat_id=chat_ident):
        try:
            set_chat_state(db, chat_id, "tenant_id", tid)
            if requester_id is not None:
                set_chat_state(db, chat_id, "last_requester_id", str(requester_id).strip())
        except Exception:
            pass
        ew = (entry_worker_id or "").strip()
        if ew and ew.lower() != "manager" and db is not None:
            try:
                from duckclaw.workers.discovery import list_workers_for_fly

                canonical = _resolve_template_id(list_workers_for_fly(tenant_id=tid), ew)
                if canonical:
                    set_chat_state(db, chat_id, "worker_id", canonical)
            except Exception:
                pass
        out = _dispatch_fly_command(
            db,
            chat_id,
            name,
            args,
            requester_id=requester_id,
            tenant_id=tenant_id,
            vault_user_id=vault_user_id,
            username=username or "",
            entry_worker_id=entry_worker_id,
        )
        if out is not None:
            log_fly(_fly_log, "/%s -> %s", name, _fly_reply_preview(out))
        return out
