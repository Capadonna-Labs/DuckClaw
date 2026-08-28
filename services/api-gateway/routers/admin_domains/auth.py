from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, field_validator

from routers.admin_domains.admin_common import problem

router = APIRouter(prefix="/auth", tags=["admin-auth"])
_log = logging.getLogger(__name__)


class AdminLoginBody(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return (v or "").strip().lower()

    @field_validator("password")
    @classmethod
    def password_length(cls, v: str) -> str:
        if len(v) < 8 or len(v) > 128:
            raise ValueError("invalid password length")
        if "\r" in v or "\n" in v:
            raise ValueError("invalid password characters")
        return v


class AdminRegisterBody(AdminLoginBody):
    nombre: str = ""


async def admin_auth_register_impl(body: AdminRegisterBody) -> dict[str, Any]:
    """Create the first local administrator through the singleton DB writer."""
    from duckclaw import DuckClaw
    from duckclaw.admin_console_users import count_console_users
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.write_commands import UpsertConsoleUserCommand

    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise problem(503, "Gateway DuckDB no disponible", gw)

    db = DuckClaw(gw, read_only=True, engine="python")
    try:
        has_users = count_console_users(db) > 0
    finally:
        db.close()
    if has_users:
        raise HTTPException(
            status_code=409,
            detail="El registro inicial ya fue completado. Un administrador puede crear más cuentas desde Accesos.",
        )

    from duckclaw.gateway_enqueue import enqueue_admin_command

    try:
        task_id = enqueue_admin_command(
            UpsertConsoleUserCommand(
                actor_email="bootstrap",
                tenant_id="default",
                email=body.email,
                nombre=body.nombre.strip() or body.email,
                rol="admin",
                password=body.password,
                initials="",
                active=True,
            )
        )
    except (RuntimeError, ValueError) as exc:
        raise problem(503, "No se pudo crear la cuenta inicial", str(exc)) from exc
    return {"ok": True, "task_id": task_id, "email": body.email}


async def admin_auth_login_impl(body: AdminLoginBody, request: Request, response: Response) -> dict[str, Any]:
    from core.admin_auth import (
        apply_login_delay,
        check_ip_rate_limit,
        clear_email_failures,
        client_ip,
        create_session,
        record_email_failure,
        set_auth_cookies,
    )
    from duckclaw import DuckClaw
    from duckclaw import db_write_queue
    from duckclaw.admin_console_users import (
        authenticate_console_user_readonly,
        console_users_seed_required,
        default_seed_users,
    )
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.write_commands import (
        ClearAdminLoginFailuresCommand,
        RecordAdminLoginFailureCommand,
        UpdateConsoleUserPasswordHashCommand,
        UpsertConsoleUserCommand,
    )

    from duckclaw.lite_session_store import admin_session_backend

    session_backend = admin_session_backend(request.app.state)
    ip = client_ip(request)
    if session_backend is not None:
        await check_ip_rate_limit(session_backend, ip)
        await apply_login_delay(session_backend, body.email)

    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise problem(503, "Gateway DuckDB no disponible", gw)

    from core.admin_identity import attach_profile_to_console_user, console_user_public

    def _enqueue_auth_command(command: Any) -> str:
        from duckclaw.gateway_enqueue import enqueue_admin_command

        return enqueue_admin_command(command)

    def _seed_required() -> bool:
        try:
            db = DuckClaw(gw, read_only=True, engine="python")
            try:
                return console_users_seed_required(db)
            finally:
                db.close()
        except Exception as exc:
            _log.warning("console seed check skipped: %s", exc)
            return False

    should_seed = await asyncio.to_thread(_seed_required)

    if should_seed:
        for seed_user in default_seed_users():
            _enqueue_auth_command(
                UpsertConsoleUserCommand(
                    tenant_id="default",
                    actor_email="system",
                    email=seed_user["email"],
                    nombre=seed_user.get("nombre") or seed_user["email"],
                    rol=seed_user.get("rol") or "user",
                    password=seed_user.get("password") or "",
                    initials=seed_user.get("initials") or "",
                    active=True,
                )
            )

    def _authenticate() -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        db = DuckClaw(gw, read_only=True, engine="python")
        try:
            found, pwd_update = authenticate_console_user_readonly(
                db, email=body.email, password=body.password
            )
            if found:
                found = attach_profile_to_console_user(db, found)
            return found, pwd_update
        finally:
            db.close()

    try:
        user, password_update = await asyncio.to_thread(_authenticate)
    except Exception as exc:
        msg = str(exc).lower()
        if "lock" in msg or "conflicting" in msg or "different configuration" in msg:
            raise problem(503, "Gateway ocupado. Reintenta el login.", str(exc)[:200]) from exc
        raise

    if not user:
        try:
            _enqueue_auth_command(
                RecordAdminLoginFailureCommand(
                    tenant_id="default",
                    actor_email="system",
                    email=body.email,
                )
            )
        except RuntimeError as exc:
            raise problem(503, "DB-writer rechazó fallo de login", str(exc)) from exc
        if session_backend is not None:
            await record_email_failure(session_backend, body.email)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    try:
        if password_update:
            _enqueue_auth_command(
                UpdateConsoleUserPasswordHashCommand(
                    tenant_id="default",
                    actor_email=str(user.get("email") or "system"),
                    email=str(password_update.get("email") or body.email),
                    password_hash=str(password_update.get("password_hash") or ""),
                    hash_algo=str(password_update.get("hash_algo") or "argon2id"),
                    hash_params=dict(password_update.get("hash_params") or {}),
                )
            )
        _enqueue_auth_command(
            ClearAdminLoginFailuresCommand(
                tenant_id="default",
                actor_email=str(user.get("email") or "system"),
                email=body.email,
            )
        )
    except RuntimeError as exc:
        raise problem(503, "DB-writer rechazó estado de login", str(exc)) from exc

    if session_backend is None:
        raise problem(503, "Redis no disponible para sesiones", "redis")
    await clear_email_failures(session_backend, body.email)
    session_id, csrf_token = await create_session(session_backend, user=user)
    set_auth_cookies(response, session_id, csrf_token, request=request)
    _log.info("login_success email=%s ip=%s", body.email, ip)
    return {"user": console_user_public(user)}


@router.post("/login")
async def admin_auth_login(body: AdminLoginBody, request: Request, response: Response) -> dict[str, Any]:
    return await admin_auth_login_impl(body, request, response)


@router.post("/register")
async def admin_auth_register(body: AdminRegisterBody) -> dict[str, Any]:
    return await admin_auth_register_impl(body)


@router.get("/me")
async def admin_auth_me(request: Request) -> dict[str, Any]:
    from core.admin_auth import SESSION_COOKIE, destroy_session, load_session, refresh_session, session_user_public
    from core.admin_identity import attach_profile_to_console_user, open_gateway_db
    from duckclaw.admin_console_users import get_by_email

    from duckclaw.lite_session_store import admin_session_backend

    session_backend = admin_session_backend(request.app.state)
    session_id = request.cookies.get(SESSION_COOKIE)
    if not session_backend or not session_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    session = await load_session(session_backend, session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired")

    email = str(session.get("email") or "").strip()
    if not email:
        await destroy_session(session_backend, session_id)
        raise HTTPException(status_code=401, detail="Session user missing")

    def _resolve_session_from_db() -> dict[str, Any] | None:
        from duckclaw.admin_console_users import console_user_is_active

        with open_gateway_db(read_only=True) as db:
            user = get_by_email(db, email)
            if not user:
                # ponytail: _query_all_dicts swallows lock/read errors as [].
                # Empty lookup is ambiguous (missing vs hub busy) — raise so we
                # keep Redis session instead of destroying it.
                raise RuntimeError("auth_me: console user lookup empty")
            if not console_user_is_active(user):
                return None
            public_user = {
                **session,
                "email": user.get("email"),
                "nombre": user.get("nombre"),
                "rol": user.get("rol"),
                "initials": user.get("initials") or "",
            }
            return attach_profile_to_console_user(db, public_user)

    try:
        resolved = await asyncio.to_thread(_resolve_session_from_db)
    except Exception as exc:
        _log.warning("auth_me_db_fallback email=%s err=%s", email, exc)
        session = await refresh_session(session_backend, session_id, session)
        return {"user": session_user_public(session)}
    if resolved is None:
        await destroy_session(session_backend, session_id)
        raise HTTPException(status_code=401, detail="Session user not active")
    session = resolved

    session = await refresh_session(session_backend, session_id, session)
    if not (session.get("profile") or {}).get("tenant_id") and email:

        def _attach_profile() -> dict[str, Any]:
            with open_gateway_db(read_only=True) as db:
                return attach_profile_to_console_user(db, dict(session))

        session = await asyncio.to_thread(_attach_profile)
    return {"user": session_user_public(session)}


@router.post("/logout")
async def admin_auth_logout(request: Request, response: Response) -> dict[str, Any]:
    from core.admin_auth import SESSION_COOKIE, clear_auth_cookies, destroy_session

    from duckclaw.lite_session_store import admin_session_backend

    session_backend = admin_session_backend(request.app.state)
    session_id = request.cookies.get(SESSION_COOKIE)
    if session_backend and session_id:
        await destroy_session(session_backend, session_id)
    clear_auth_cookies(response)
    return {"ok": True}
