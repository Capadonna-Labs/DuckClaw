from __future__ import annotations

import re
import time
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/sandbox", tags=["admin-sandbox-sessions"])


class NovncPrepareBody(BaseModel):
    chat_id: str | None = Field(default=None, max_length=128)
    worker_id: str | None = Field(default=None, max_length=64)
    tenant_id: str | None = Field(default=None, max_length=64)


class SandboxNetworkBody(BaseModel):
    chat_id: str = Field(..., min_length=1, max_length=128)
    enabled: bool
    worker_id: str | None = Field(default=None, max_length=64)
    tenant_id: str | None = Field(default=None, max_length=64)


def require_admin_key(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> None:
    from routers import admin as admin_router

    admin_router._require_admin_key(x_admin_key)


def _problem(status_code: int, title: str, detail: str) -> HTTPException:
    from routers import admin as admin_router

    return admin_router._problem(status_code, title, detail)


def _worker_has_browser_sandbox(worker_id: str) -> bool:
    from duckclaw.workers.manifest import load_manifest

    wid = re.sub(r"[^a-zA-Z0-9_-]", "", (worker_id or "").strip())
    if not wid:
        return False
    try:
        spec = load_manifest(wid)
        return bool(getattr(spec, "browser_sandbox", False))
    except Exception:
        return False


def _sandbox_chat_policy_payload(
    *,
    chat_id: str,
    worker_id: str,
    vault_path: str,
    tenant_id: str,
) -> dict[str, Any]:
    from duckclaw.forge.schema import resolve_sandbox_network_policy
    from duckclaw.graphs.on_the_fly_commands import get_chat_state
    from duckclaw.workers.manifest import load_manifest
    from routers import admin as admin_router

    db = admin_router._open_playground_vault_db(vault_path, read_only=True)
    try:
        raw_net = get_chat_state(db, chat_id, "sandbox_network_enabled")
        raw_sb = get_chat_state(db, chat_id, "sandbox_enabled")
    finally:
        db.close()

    _, meta = resolve_sandbox_network_policy(worker_id, raw_net or None)
    browser_sandbox = False
    try:
        browser_sandbox = bool(load_manifest(worker_id).browser_sandbox)
    except Exception:
        browser_sandbox = False

    return {
        "chat_id": chat_id,
        "worker_id": worker_id,
        "tenant_id": tenant_id,
        "vault_path": vault_path,
        "sandbox_enabled": (raw_sb or "").strip().lower() in ("true", "1", "on", "yes", "si", "sí"),
        "sandbox_network_enabled": (raw_net or "").strip().lower() or None,
        "yaml_network_default": meta.get("yaml_default"),
        "effective_network": meta.get("effective"),
        "network_toggle_available": bool(meta.get("toggle_available")),
        "browser_sandbox": browser_sandbox,
    }


@router.get("/chat-policy", dependencies=[Depends(require_admin_key)])
async def admin_sandbox_chat_policy(
    chat_id: str = Query(..., min_length=1, max_length=128),
    worker_id: str | None = Query(None, max_length=64),
    tenant_id: str | None = Query(None, max_length=64),
) -> dict[str, Any]:
    """Estado sandbox + red efectiva para un chat del admin playground."""
    from routers import admin as admin_router

    team_ctx = admin_router._playground_team_context(tenant_id=tenant_id, chat_id=chat_id)
    if not team_ctx.get("authorized"):
        raise _problem(403, "No autorizado", str(team_ctx.get("team_hint") or ""))

    wid = admin_router._pick_playground_worker(team_ctx, worker_id)

    try:
        vault_path = admin_router._playground_vault_db_path(team_ctx, wid)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc

    return _sandbox_chat_policy_payload(
        chat_id=chat_id.strip(),
        worker_id=wid,
        vault_path=vault_path,
        tenant_id=str(team_ctx.get("tenant_id") or "default"),
    )


@router.post("/network", dependencies=[Depends(require_admin_key)])
async def admin_sandbox_network_toggle(body: SandboxNetworkBody) -> dict[str, Any]:
    """Activa/desactiva internet en sandbox para un chat (respeta security_policy.yaml)."""
    from duckclaw.forge.schema import resolve_sandbox_network_policy
    from duckclaw.graphs.on_the_fly_commands import get_chat_state, set_chat_state_via_vault
    from duckclaw.graphs.sandbox import cleanup_sandbox_session_for_chat
    from routers import admin as admin_router

    team_ctx = admin_router._playground_team_context(tenant_id=body.tenant_id, chat_id=body.chat_id)
    if not team_ctx.get("authorized"):
        raise _problem(403, "No autorizado", str(team_ctx.get("team_hint") or ""))

    chat_raw = body.chat_id.strip()
    wid = admin_router._pick_playground_worker(team_ctx, body.worker_id)

    try:
        vault_path = admin_router._playground_vault_db_path(team_ctx, wid)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc

    db = admin_router._open_playground_vault_db(vault_path, read_only=True)
    try:
        raw_prev = get_chat_state(db, chat_raw, "sandbox_network_enabled")
        _, meta = resolve_sandbox_network_policy(wid, raw_prev or None)
        if not meta.get("toggle_available"):
            raise _problem(
                400,
                "Worker sin red en política",
                f"«{wid}» tiene network.default=deny en security_policy.yaml. "
                "Elige un worker con red habilitada en su política o ajusta el manifest.",
            )
        tid = str(team_ctx.get("tenant_id") or "default").strip() or "default"
        val = "true" if body.enabled else "false"
        ok, err = set_chat_state_via_vault(
            db, chat_raw, "sandbox_network_enabled", val, tenant_id=tid
        )
    finally:
        db.close()

    if not ok:
        raise _problem(500, "No se pudo persistir", err or "set_chat_state_via_vault failed")

    cleanup_sandbox_session_for_chat(chat_raw)
    policy = _sandbox_chat_policy_payload(
        chat_id=chat_raw,
        worker_id=wid,
        vault_path=vault_path,
        tenant_id=str(team_ctx.get("tenant_id") or "default"),
    )
    return {"ok": True, "recreated": True, **policy}


@router.get("/status", dependencies=[Depends(require_admin_key)])
async def admin_sandbox_status() -> dict[str, Any]:
    """Requisitos Docker/noVNC para la pestaña VNC del admin."""
    from duckclaw.graphs.sandbox import sandbox_runtime_status

    st = sandbox_runtime_status()
    ready = bool(st.get("docker_available")) and bool(st.get("publish_novnc"))
    hints: list[str] = []
    if not st.get("docker_available"):
        hints.append("Docker no disponible en el host del gateway.")
    if not st.get("publish_novnc"):
        hints.append("Define STRIX_BROWSER_PUBLISH_NOVNC=1 y reinicia DuckClaw-Gateway.")
    if not st.get("public_url"):
        hints.append(
            "Sin DUCKCLAW_PUBLIC_URL: el iframe usará http://127.0.0.1:<puerto> (solo mismo host)."
        )
    return {"ready": ready, "hints": hints, **st}


@router.get("/sessions", dependencies=[Depends(require_admin_key)])
async def admin_sandbox_sessions() -> dict[str, Any]:
    """Contenedores strix_sandbox_* y sesiones noVNC activas."""
    from duckclaw.graphs.sandbox import list_strix_sandbox_containers

    containers = list_strix_sandbox_containers()
    return {"containers": containers, "count": len(containers)}


@router.post("/novnc/prepare", dependencies=[Depends(require_admin_key)])
async def admin_sandbox_novnc_prepare(body: NovncPrepareBody) -> dict[str, Any]:
    """Levanta o reutiliza browser sandbox y devuelve URL noVNC para el admin."""
    from duckclaw.graphs.novnc_registry import (
        get_session_expires_at,
        sanitize_chat_to_session_id,
        touch,
    )
    from duckclaw.graphs.sandbox import ensure_browser_novnc_session, sandbox_runtime_status
    from routers import admin as admin_router

    st = sandbox_runtime_status()
    if not st.get("docker_available"):
        raise _problem(503, "Docker no disponible", "El gateway no puede contactar Docker.")
    if not st.get("publish_novnc"):
        raise _problem(
            503,
            "noVNC deshabilitado",
            "STRIX_BROWSER_PUBLISH_NOVNC no está activo en el proceso del gateway.",
        )

    team_ctx = admin_router._playground_team_context(tenant_id=body.tenant_id)
    chat_raw = (body.chat_id or team_ctx.get("team_chat_id") or "admin-playground").strip()
    session_id = sanitize_chat_to_session_id(chat_raw)
    wid = admin_router._pick_playground_worker(team_ctx, body.worker_id, require_browser_sandbox=True)
    if not _worker_has_browser_sandbox(wid):
        raise _problem(
            400,
            "Worker sin browser sandbox",
            f"El worker '{wid}' no tiene browser_sandbox: true en manifest.yaml.",
        )

    policy_db = None
    try:
        vault_path = admin_router._playground_vault_db_path(team_ctx, wid)
        policy_db = admin_router._open_playground_vault_db(vault_path, read_only=True)
    except Exception:
        policy_db = None
    try:
        vnc_url = ensure_browser_novnc_session(
            wid,
            session_id,
            db=policy_db,
            chat_id=chat_raw,
        )
    finally:
        if policy_db is not None:
            try:
                policy_db.close()
            except Exception:
                pass
    if not vnc_url:
        raise _problem(
            503,
            "No se pudo preparar noVNC",
            "Revisa logs del gateway, imagen duckclaw/browser-env y política del worker.",
        )

    touch(session_id)
    expires_at = get_session_expires_at(session_id)
    return {
        "session_id": session_id,
        "chat_id": chat_raw,
        "worker_id": wid,
        "vnc_url": vnc_url,
        "expires_at": expires_at,
        "seconds_remaining": max(0.0, float(expires_at or 0) - time.time()) if expires_at else None,
    }
