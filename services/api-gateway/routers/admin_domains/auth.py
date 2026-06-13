from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, field_validator

router = APIRouter(prefix="/auth", tags=["admin-auth"])


class AdminLoginBody(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return (value or "").strip().lower()

    @field_validator("password")
    @classmethod
    def password_min_length(cls, value: str) -> str:
        if len(value or "") < 8:
            raise ValueError("password too short")
        return value


@router.post("/login")
async def admin_auth_login(body: AdminLoginBody, request: Request, response: Response) -> dict[str, Any]:
    from routers import admin as admin_router

    return await admin_router._admin_auth_login_impl(body, request, response)


@router.get("/me")
async def admin_auth_me(request: Request) -> dict[str, Any]:
    from core.admin_auth import SESSION_COOKIE, destroy_session, load_session, refresh_session, session_user_public
    from core.admin_identity import attach_profile_to_console_user, open_gateway_db
    from duckclaw.admin_console_users import get_by_email

    redis_client = getattr(request.app.state, "redis", None)
    session_id = request.cookies.get(SESSION_COOKIE)
    if not redis_client or not session_id:
        raise HTTPException(status_code=401, detail="Unauthorized")

    session = await load_session(redis_client, session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Session expired")

    email = str(session.get("email") or "").strip()
    if not email:
        await destroy_session(redis_client, session_id)
        raise HTTPException(status_code=401, detail="Session user missing")

    with open_gateway_db(read_only=True) as db:
        user = get_by_email(db, email)
        if not user or not bool(user.get("active", True)):
            await destroy_session(redis_client, session_id)
            raise HTTPException(status_code=401, detail="Session user not active")
        public_user = {
            **session,
            "email": user.get("email"),
            "nombre": user.get("nombre"),
            "rol": user.get("rol"),
            "initials": user.get("initials") or "",
        }
        session = attach_profile_to_console_user(db, public_user)

    session = await refresh_session(redis_client, session_id, session)
    if not (session.get("profile") or {}).get("tenant_id") and email:
        with open_gateway_db(read_only=True) as db:
            session = attach_profile_to_console_user(db, dict(session))
    return {"user": session_user_public(session)}


@router.post("/logout")
async def admin_auth_logout(request: Request, response: Response) -> dict[str, Any]:
    from core.admin_auth import SESSION_COOKIE, clear_auth_cookies, destroy_session

    redis_client = getattr(request.app.state, "redis", None)
    session_id = request.cookies.get(SESSION_COOKIE)
    if redis_client and session_id:
        await destroy_session(redis_client, session_id)
    clear_auth_cookies(response)
    return {"ok": True}
