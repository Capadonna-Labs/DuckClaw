from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel

router = APIRouter(prefix="/runtime", tags=["admin-runtime-config"])

_REPO_ROOT = Path(__file__).resolve().parents[4]

_AGENT_CONFIG_DDL = """
CREATE TABLE IF NOT EXISTS agent_config (
    key VARCHAR PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


class RuntimeConfigPutBody(BaseModel):
    vault_path: str
    chat_id: str = "default"
    key: str
    value: str


def require_admin_key(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> None:
    expected = (os.environ.get("DUCKCLAW_ADMIN_API_KEY") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DUCKCLAW_ADMIN_API_KEY no configurada en el gateway",
        )
    if (x_admin_key or "").strip() != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin key inválida")


def actor_from_header(x_actor: str | None = Header(None, alias="X-Duckclaw-Actor")) -> str:
    raw = (x_actor or "").strip()[:128]
    if raw and raw != "admin-ui":
        return raw
    admin_email = os.environ.get("DUCKCLAW_ADMIN_EMAIL", "").strip()
    if admin_email and "@" in admin_email:
        return admin_email[:128]
    return raw or "admin-ui"


def _repo_root() -> Path:
    raw = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
    return Path(raw) if raw else _REPO_ROOT


def _problem(status_code: int, title: str, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"type": "about:blank", "title": title, "status": status_code, "detail": detail},
    )


def _admin_audit(
    action: str,
    resource: str,
    detail: str,
    *,
    actor: str = "admin-ui",
    meta: dict[str, Any] | None = None,
) -> None:
    from routers import admin as admin_router

    admin_router._admin_audit(action, resource, detail, actor=actor, meta=meta)


def _chat_config_prefix(chat_id: str) -> str:
    cid = (chat_id or "default").strip() or "default"
    try:
        int(cid)
        return f"chat_{cid}_"
    except ValueError:
        return f"chat_{cid[:64]}_"


def _full_agent_config_key(chat_id: str, key: str) -> str:
    k = (key or "").strip()
    if k.startswith("chat_"):
        return k[:256]
    return f"{_chat_config_prefix(chat_id)}{k}"[:256]


def _parse_agent_config_rows(raw: Any, chat_id: str) -> list[dict[str, str]]:
    rows = raw
    if isinstance(raw, str):
        rows = json.loads(raw) if raw.strip().startswith("[") else []
    if not isinstance(rows, list):
        return []
    prefix = _chat_config_prefix(chat_id)
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        full = str(row.get("key") or "")
        val = str(row.get("value") or "")
        if full.startswith(prefix):
            out.append({"key": full[len(prefix) :], "full_key": full, "value": val, "scope": "chat"})
        elif not full.startswith("chat_"):
            out.append({"key": full, "full_key": full, "value": val, "scope": "global"})
    return out


def _absolute_vault_path(vault_path: str) -> str:
    abs_path = vault_path
    if not os.path.isabs(abs_path):
        abs_path = str(_repo_root() / vault_path.lstrip("/"))
    return abs_path


def _enqueue_runtime_config_command(command: Any, *, db_path: str, actor: str) -> str:
    from core.admin_identity import vault_user_id_for_actor
    from duckclaw.db_write_queue import enqueue_typed_command, poll_task_status_sync

    user_id = vault_user_id_for_actor(actor)
    task_id = enqueue_typed_command(command, db_path=db_path, user_id=user_id)
    command_status = poll_task_status_sync(task_id, timeout_sec=0.5)
    if command_status and command_status.status == "failed":
        raise ValueError(command_status.detail or "runtime config write failed")
    return task_id


@router.get("/vaults", dependencies=[Depends(require_admin_key)])
async def list_vaults(
    vault_user_id: str | None = Query(None, description="Filtra private/ al usuario; shared siempre"),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import vault_user_id_for_actor
    from duckclaw.vaults import list_vault_options_for_user

    uid = (vault_user_id or "").strip() or vault_user_id_for_actor(actor)
    options = list_vault_options_for_user(uid)
    vaults = [{"path": o["path"], "scope": o["scope"], "vault_id": o.get("vault_id") or ""} for o in options]
    return {"vaults": vaults, "vault_user_id": uid}


@router.get("/config", dependencies=[Depends(require_admin_key)])
async def get_runtime_config(
    vault_path: str = Query(...),
    chat_id: str = Query("default"),
) -> dict[str, Any]:
    from duckclaw import DuckClaw

    abs_path = _absolute_vault_path(vault_path)
    if not os.path.isfile(abs_path):
        raise _problem(404, "Vault no encontrado", vault_path)
    db = DuckClaw(abs_path, read_only=True, engine="python")
    warning: str | None = None
    try:
        try:
            db.execute(_AGENT_CONFIG_DDL)
        except Exception:
            pass
        raw = db.query("SELECT key, value FROM agent_config ORDER BY key")
        rows = _parse_agent_config_rows(raw, chat_id)
    except Exception as exc:
        msg = str(exc)
        if "agent_config" in msg.lower() and "does not exist" in msg.lower():
            rows = []
            warning = (
                "La tabla agent_config no existe en esta bóveda. "
                "Ejecuta: uv run python scripts/bootstrap_dbs.py"
            )
        else:
            raise _problem(400, "Error leyendo agent_config", msg) from exc
    finally:
        db.close()
    out: dict[str, Any] = {"vault_path": vault_path, "chat_id": chat_id, "rows": rows}
    if warning:
        out["warning"] = warning
    return out


@router.put("/config", dependencies=[Depends(require_admin_key)])
async def put_runtime_config(
    body: RuntimeConfigPutBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.write_commands import UpsertAgentConfigEntriesCommand

    abs_path = _absolute_vault_path(body.vault_path)
    full_key = _full_agent_config_key(body.chat_id, body.key)
    command = UpsertAgentConfigEntriesCommand(
        tenant_id="default",
        actor_email=actor,
        entries={full_key: body.value[:8000]},
    )
    task_id = _enqueue_runtime_config_command(command, db_path=abs_path, actor=actor)
    _admin_audit(
        "runtime.config.put",
        body.vault_path,
        full_key,
        actor=actor,
        meta={"chat_id": body.chat_id},
    )
    return {"ok": True, "queued": True, "full_key": full_key, "task_id": task_id}


@router.delete("/config", dependencies=[Depends(require_admin_key)])
async def delete_runtime_config(
    vault_path: str = Query(...),
    chat_id: str = Query("default"),
    key: str = Query(...),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.write_commands import DeleteAgentConfigEntriesCommand

    abs_path = _absolute_vault_path(vault_path)
    full_key = _full_agent_config_key(chat_id, key)
    command = DeleteAgentConfigEntriesCommand(
        tenant_id="default",
        actor_email=actor,
        keys=[full_key],
    )
    task_id = _enqueue_runtime_config_command(command, db_path=abs_path, actor=actor)
    _admin_audit(
        "runtime.config.delete",
        vault_path,
        full_key,
        actor=actor,
        meta={"chat_id": chat_id},
    )
    return {"ok": True, "queued": True, "full_key": full_key, "task_id": task_id}
