from __future__ import annotations

import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel

router = APIRouter(tags=["admin-access-management"])


class ConsoleUserBody(BaseModel):
    email: str
    nombre: str = ""
    rol: str = "user"
    password: str | None = None
    initials: str = ""
    active: bool = True


class ConsoleUserPatchBody(BaseModel):
    nombre: str | None = None
    rol: str | None = None
    password: str | None = None
    initials: str | None = None
    active: bool | None = None


class SharedGrantBody(BaseModel):
    tenant_id: str = "default"
    user_id: str
    resource_key: str


class WhitelistBody(BaseModel):
    user_id: str
    username: str = ""
    role: str = "user"
    tenant_id: str = ""


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


def _problem(status_code: int, title: str, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"type": "about:blank", "title": title, "status": status_code, "detail": detail},
    )


def _gateway_effective_tenant_id(request_tenant: str | None) -> str:
    from routers import admin as admin_router

    return admin_router._gateway_effective_tenant_id(request_tenant)


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


def _enqueue_access_command(command: Any) -> str:
    from duckclaw.gateway_enqueue import enqueue_admin_command

    return enqueue_admin_command(command)


def _gateway_db_path_or_404() -> str:
    from duckclaw.gateway_db import get_gateway_db_path

    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise _problem(404, "Gateway DuckDB no encontrada", gw)
    return gw


def _get_console_user_readonly(email: str) -> tuple[dict[str, Any] | None, str]:
    from duckclaw import DuckClaw
    from duckclaw.admin_console_users import get_by_email

    gw = _gateway_db_path_or_404()
    db = DuckClaw(gw, read_only=True, engine="python")
    try:
        return get_by_email(db, email), gw
    finally:
        db.close()


def _console_user_public(
    *,
    email: str,
    nombre: str,
    rol: str,
    initials: str,
    active: bool,
) -> dict[str, Any]:
    em = (email or "").strip().lower()
    role = (rol or "user").strip().lower()
    if role == "viewer":
        role = "user"
    return {
        "email": em,
        "nombre": (nombre or em).strip(),
        "rol": role,
        "initials": (initials or em[:2]).upper()[:8],
        "active": bool(active),
    }


def _list_whitelist_users_merged(db: Any, *, tenant_id: str) -> list[dict[str, str]]:
    from duckclaw.graphs.on_the_fly_commands import (
        _dedupe_authorized_users_by_user_id,
        _list_authorized_users,
    )

    tid = (tenant_id or "default").strip() or "default"
    users = _list_authorized_users(db, tenant_id=tid)
    if tid.lower() != "default":
        legacy = _list_authorized_users(db, tenant_id="default")
        if legacy:
            users = _dedupe_authorized_users_by_user_id(users + legacy)
    return users


async def _invalidate_whitelist_cache(
    request: Request,
    *,
    tenant_id: str,
    user_id: str,
) -> None:
    from duckclaw.graphs.on_the_fly_commands import _invalidate_whitelist_redis_cache

    _invalidate_whitelist_redis_cache(tenant_id=tenant_id, user_id=user_id)
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is None:
        return
    tid = str(tenant_id or "default").strip().lower() or "default"
    uid = str(user_id or "").strip()
    if not uid:
        return
    key = f"whitelist:{tid}:{uid}"
    try:
        await redis_client.delete(key)
    except Exception:
        pass


@router.get("/access/overview", dependencies=[Depends(require_admin_key)])
async def get_access_overview(tenant_id: str = Query("default")) -> dict[str, Any]:
    from duckclaw import DuckClaw
    from duckclaw.admin_console_users import count_console_users
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.graphs.on_the_fly_commands import _list_authorized_users
    from duckclaw.shared_db_grants import list_shared_grants_for_tenant

    tid = _gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    gw = (get_gateway_db_path() or "").strip()
    console_count = 0
    telegram_count = 0
    shared_count = 0
    if gw and os.path.isfile(gw):
        db = DuckClaw(gw, read_only=True, engine="python")
        try:
            console_count = count_console_users(db)
            users = _list_authorized_users(db, tenant_id=tid)
            telegram_count = len(users)
            shared_count = len(list_shared_grants_for_tenant(db, tenant_id=tid))
        finally:
            db.close()
    return {
        "tenant_id": tid,
        "console_users": console_count,
        "telegram_users": telegram_count,
        "shared_grants": shared_count,
        "db_path": gw,
        "db_exists": bool(gw and os.path.isfile(gw)),
        "persistence_tables": {
            "console": "main.admin_console_users",
            "telegram": "main.authorized_users",
            "shared": "main.user_shared_db_access",
        },
    }


@router.get("/console-users", dependencies=[Depends(require_admin_key)])
async def list_admin_console_users() -> dict[str, Any]:
    from duckclaw import DuckClaw
    from duckclaw.admin_console_users import list_console_users
    from duckclaw.gateway_db import get_gateway_db_path

    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        return {"users": [], "db_path": gw, "warning": "Gateway DuckDB no encontrada"}
    db = DuckClaw(gw, read_only=True, engine="python")
    try:
        users = list_console_users(db)
    finally:
        db.close()
    return {"users": users, "db_path": gw}


@router.post("/console-users", dependencies=[Depends(require_admin_key)])
async def create_admin_console_user(
    body: ConsoleUserBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.write_commands import UpsertConsoleUserCommand

    gw = _gateway_db_path_or_404()
    if not (body.password or "").strip():
        raise _problem(400, "password requerido", body.email)
    try:
        task_id = _enqueue_access_command(
            UpsertConsoleUserCommand(
                actor_email=actor,
                tenant_id="default",
                email=body.email,
                nombre=body.nombre,
                rol=body.rol,
                password=body.password,
                initials=body.initials,
                active=body.active,
            )
        )
        user = _console_user_public(
            email=body.email,
            nombre=body.nombre,
            rol=body.rol,
            initials=body.initials,
            active=body.active,
        )
    except RuntimeError as exc:
        raise _problem(503, "DB-writer rechazó console user", str(exc)) from exc
    except ValueError as exc:
        raise _problem(400, str(exc), body.email) from exc
    _admin_audit("console.user.upsert", body.email, body.rol, actor=actor)
    return {"ok": True, "user": user, "db_path": gw, "task_id": task_id}


@router.patch("/console-users", dependencies=[Depends(require_admin_key)])
async def patch_admin_console_user(
    email: str = Query(...),
    body: ConsoleUserPatchBody = ...,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.write_commands import UpsertConsoleUserCommand

    em = (email or "").strip()
    if not em:
        raise _problem(400, "email requerido", "")
    existing, gw = _get_console_user_readonly(em)
    if not existing:
        raise _problem(404, "Usuario no encontrado", em)
    nombre = body.nombre if body.nombre is not None else str(existing.get("nombre") or "")
    rol = body.rol if body.rol is not None else str(existing.get("rol") or "user")
    initials = body.initials if body.initials is not None else str(existing.get("initials") or "")
    active = body.active if body.active is not None else bool(existing.get("active", True))
    try:
        task_id = _enqueue_access_command(
            UpsertConsoleUserCommand(
                actor_email=actor,
                tenant_id="default",
                email=em,
                nombre=nombre,
                rol=rol,
                password=body.password,
                initials=initials,
                active=active,
            )
        )
        user = _console_user_public(
            email=em,
            nombre=nombre,
            rol=rol,
            initials=initials,
            active=active,
        )
    except RuntimeError as exc:
        raise _problem(503, "DB-writer rechazó console user", str(exc)) from exc
    except ValueError as exc:
        raise _problem(400, str(exc), em) from exc
    _admin_audit("console.user.patch", em, body.rol or "", actor=actor)
    return {"ok": True, "user": user, "db_path": gw, "task_id": task_id}


@router.delete("/console-users", dependencies=[Depends(require_admin_key)])
async def delete_admin_console_user(
    email: str = Query(...),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.write_commands import DeactivateConsoleUserCommand

    em = (email or "").strip()
    if not em:
        raise _problem(400, "email requerido", "")
    existing, gw = _get_console_user_readonly(em)
    if not existing:
        raise _problem(404, "Usuario no encontrado", em)
    try:
        task_id = _enqueue_access_command(
            DeactivateConsoleUserCommand(actor_email=actor, tenant_id="default", email=em)
        )
    except RuntimeError as exc:
        raise _problem(503, "DB-writer rechazó console user", str(exc)) from exc
    _admin_audit("console.user.deactivate", em, "", actor=actor)
    return {"ok": True, "email": em, "db_path": gw, "task_id": task_id}


@router.get("/access/shared-grants", dependencies=[Depends(require_admin_key)])
async def get_shared_grants(tenant_id: str = Query("default")) -> dict[str, Any]:
    from duckclaw import DuckClaw
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.shared_db_grants import list_shared_grants_for_tenant

    tid = _gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        return {"tenant_id": tid, "grants": [], "db_path": gw, "warning": "Gateway DuckDB no encontrada"}
    db = DuckClaw(gw, read_only=True, engine="python")
    try:
        grants = list_shared_grants_for_tenant(db, tenant_id=tid)
    finally:
        db.close()
    return {"tenant_id": tid, "grants": grants, "db_path": gw}


@router.post("/access/shared-grants", dependencies=[Depends(require_admin_key)])
async def post_shared_grant(
    body: SharedGrantBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.shared_db_grants import validate_resource_key
    from duckclaw.write_commands import UpsertSharedDbGrantCommand

    tid = _gateway_effective_tenant_id((body.tenant_id or "default").strip() or "default")
    uid = (body.user_id or "").strip()
    rk = (body.resource_key or "").strip().lower()
    if not uid:
        raise _problem(400, "user_id requerido", "")
    if not validate_resource_key(rk):
        raise _problem(400, "resource_key inválido", rk)
    gw = _gateway_db_path_or_404()
    try:
        task_id = _enqueue_access_command(
            UpsertSharedDbGrantCommand(
                tenant_id=tid,
                actor_email=actor,
                user_id=uid,
                resource_key=rk,
            )
        )
    except RuntimeError as exc:
        raise _problem(503, "DB-writer rechazó shared grant", str(exc)) from exc
    _admin_audit("access.shared.grant", f"tenant:{tid}", f"{uid}:{rk}", actor=actor)
    return {"ok": True, "tenant_id": tid, "user_id": uid, "resource_key": rk, "db_path": gw, "task_id": task_id}


@router.delete("/access/shared-grants", dependencies=[Depends(require_admin_key)])
async def delete_shared_grant(
    tenant_id: str = Query("default"),
    user_id: str = Query(...),
    resource_key: str = Query(...),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.shared_db_grants import validate_resource_key
    from duckclaw.write_commands import DeleteSharedDbGrantCommand

    tid = _gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    uid = (user_id or "").strip()
    rk = (resource_key or "").strip().lower()
    if not uid or not rk:
        raise _problem(400, "user_id y resource_key requeridos", "")
    if not validate_resource_key(rk):
        raise _problem(400, "resource_key inválido", rk)
    gw = _gateway_db_path_or_404()
    try:
        task_id = _enqueue_access_command(
            DeleteSharedDbGrantCommand(
                tenant_id=tid,
                actor_email=actor,
                user_id=uid,
                resource_key=rk,
            )
        )
    except RuntimeError as exc:
        raise _problem(503, "DB-writer rechazó shared grant", str(exc)) from exc
    _admin_audit("access.shared.revoke", f"tenant:{tid}", f"{uid}:{rk}", actor=actor)
    return {"ok": True, "tenant_id": tid, "user_id": uid, "resource_key": rk, "db_path": gw, "task_id": task_id}


@router.get("/telegram/whitelist", dependencies=[Depends(require_admin_key)])
async def get_telegram_whitelist(tenant_id: str = Query("default")) -> dict[str, Any]:
    from duckclaw import DuckClaw
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.graphs.on_the_fly_commands import _ensure_authorized_users_table

    requested = (tenant_id or "default").strip() or "default"
    tid = _gateway_effective_tenant_id(requested)
    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        return {
            "tenant_id": tid,
            "requested_tenant_id": requested,
            "effective_tenant_id": tid,
            "users": [],
            "db_path": gw,
            "warning": "Gateway DuckDB no encontrada",
        }
    db = DuckClaw(gw, read_only=True, engine="python")
    try:
        _ensure_authorized_users_table(db)
        users = _list_whitelist_users_merged(db, tenant_id=tid)
    finally:
        db.close()
    hint = None
    if requested.lower() == "default" and tid.lower() != "default":
        hint = (
            f"El gateway usa tenant «{tid}» (env explícito o runtime settings DB-first). "
            "Los usuarios deben estar en este tenant para pasar el Telegram Guard."
        )
    return {
        "tenant_id": tid,
        "requested_tenant_id": requested,
        "effective_tenant_id": tid,
        "users": users,
        "db_path": gw,
        "hint": hint,
    }


@router.post("/telegram/whitelist", dependencies=[Depends(require_admin_key)])
async def post_telegram_whitelist(
    body: WhitelistBody,
    request: Request,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.write_commands import UpsertAuthorizedUserCommand

    requested = (body.tenant_id or "default").strip() or "default"
    tid = _gateway_effective_tenant_id(requested)
    uid = (body.user_id or "").strip()
    if not uid:
        raise _problem(400, "user_id requerido", "")
    role = (body.role or "user").strip().lower()
    if role not in ("admin", "user"):
        raise _problem(400, "role inválido", role)
    gw = _gateway_db_path_or_404()
    try:
        task_id = _enqueue_access_command(
            UpsertAuthorizedUserCommand(
                tenant_id=tid,
                actor_email=actor,
                user_id=uid,
                username=(body.username or "Usuario").strip() or "Usuario",
                role=role,
            )
        )
    except RuntimeError as exc:
        raise _problem(503, "DB-writer rechazó whitelist", str(exc)) from exc
    await _invalidate_whitelist_cache(request, tenant_id=tid, user_id=uid)
    _admin_audit(
        "telegram.whitelist.upsert",
        f"tenant:{tid}",
        uid,
        actor=actor,
        meta={"role": role, "requested_tenant_id": requested},
    )
    return {
        "ok": True,
        "tenant_id": tid,
        "effective_tenant_id": tid,
        "requested_tenant_id": requested,
        "user_id": uid,
        "role": role,
        "db_path": gw,
        "task_id": task_id,
    }


@router.delete("/telegram/whitelist", dependencies=[Depends(require_admin_key)])
async def delete_telegram_whitelist(
    request: Request,
    tenant_id: str = Query("default"),
    user_id: str = Query(...),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.write_commands import DeleteAuthorizedUserCommand

    requested = (tenant_id or "default").strip() or "default"
    tid = _gateway_effective_tenant_id(requested)
    uid = (user_id or "").strip()
    if not uid:
        raise _problem(400, "user_id requerido", "")
    gw = _gateway_db_path_or_404()
    try:
        task_id = _enqueue_access_command(
            DeleteAuthorizedUserCommand(tenant_id=tid, actor_email=actor, user_id=uid)
        )
    except RuntimeError as exc:
        raise _problem(503, "DB-writer rechazó whitelist", str(exc)) from exc
    await _invalidate_whitelist_cache(request, tenant_id=tid, user_id=uid)
    _admin_audit("telegram.whitelist.delete", f"tenant:{tid}", uid, actor=actor)
    return {"ok": True, "tenant_id": tid, "effective_tenant_id": tid, "user_id": uid, "task_id": task_id}
