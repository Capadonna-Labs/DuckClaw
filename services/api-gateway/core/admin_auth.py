"""
Admin console auth: Redis sessions, rate limiting, cookies.

Spec: specs/features/platform/ADMIN_CONSOLE_AUTH.md
"""

from __future__ import annotations

import asyncio
import json
import os
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, Request, Response

SESSION_COOKIE = "session"
CSRF_COOKIE = "csrf_token"
SESSION_KEY_PREFIX = "sess:"
RL_IP_PREFIX = "rl:login:ip:"
RL_EMAIL_PREFIX = "rl:login:email:"


def session_ttl_seconds() -> int:
    return max(300, int(os.environ.get("SESSION_TTL_SECONDS", "43200")))


def is_production_env() -> bool:
    return (os.environ.get("ENV") or os.environ.get("NODE_ENV") or "development").strip().lower() == "production"


def cookie_domain() -> str | None:
    raw = (os.environ.get("COOKIE_DOMAIN") or "").strip()
    return raw or None


def client_ip(request: Request) -> str:
    forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if forwarded:
        return forwarded
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def set_auth_cookies(response: Response, session_id: str, csrf_token: str) -> None:
    ttl = session_ttl_seconds()
    secure = is_production_env()
    domain = cookie_domain()
    common: dict[str, Any] = {
        "max_age": ttl,
        "path": "/",
        "samesite": "lax",
        "secure": secure,
    }
    if domain:
        common["domain"] = domain
    response.set_cookie(SESSION_COOKIE, session_id, httponly=True, **common)
    response.set_cookie(CSRF_COOKIE, csrf_token, httponly=False, **common)


def clear_auth_cookies(response: Response) -> None:
    domain = cookie_domain()
    kwargs: dict[str, Any] = {"path": "/"}
    if domain:
        kwargs["domain"] = domain
    response.delete_cookie(SESSION_COOKIE, **kwargs)
    response.delete_cookie(CSRF_COOKIE, **kwargs)


async def check_ip_rate_limit(redis: Any, ip: str) -> None:
    key = f"{RL_IP_PREFIX}{ip}"
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)
    if int(count) > 100:
        raise HTTPException(status_code=429, detail="Too many attempts")


async def get_email_fail_count(redis: Any, email: str) -> int:
    raw = await redis.get(f"{RL_EMAIL_PREFIX}{email.strip().lower()}")
    return int(raw) if raw else 0


async def record_email_failure(redis: Any, email: str) -> None:
    key = f"{RL_EMAIL_PREFIX}{email.strip().lower()}"
    await redis.incr(key)
    await redis.expire(key, 86400)


async def clear_email_failures(redis: Any, email: str) -> None:
    await redis.delete(f"{RL_EMAIL_PREFIX}{email.strip().lower()}")


async def apply_login_delay(redis: Any, email: str) -> None:
    from duckclaw.admin_auth_crypto import calculate_login_delay

    fail_count = await get_email_fail_count(redis, email)
    delay = calculate_login_delay(fail_count)
    if delay > 0:
        await asyncio.sleep(min(delay, 5))


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def new_csrf_token() -> str:
    return uuid.uuid4().hex + secrets.token_hex(16)


async def create_session(redis: Any, *, user: dict[str, Any]) -> tuple[str, str]:
    session_id = new_session_id()
    csrf_token = new_csrf_token()
    ttl = session_ttl_seconds()
    now = datetime.now(timezone.utc).isoformat()
    payload = {
        "user_id": user.get("id") or f"user-{user.get('email')}",
        "email": user.get("email"),
        "nombre": user.get("nombre"),
        "rol": user.get("rol"),
        "initials": user.get("initials") or "",
        "created_at": now,
        "last_activity": now,
        "csrf_token": csrf_token,
    }
    await redis.setex(f"{SESSION_KEY_PREFIX}{session_id}", ttl, json.dumps(payload))
    return session_id, csrf_token


async def load_session(redis: Any, session_id: str) -> Optional[dict[str, Any]]:
    if not session_id:
        return None
    raw = await redis.get(f"{SESSION_KEY_PREFIX}{session_id}")
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


async def refresh_session(redis: Any, session_id: str, session: dict[str, Any]) -> dict[str, Any]:
    """Extend TTL and update last_activity."""
    ttl = session_ttl_seconds()
    session = dict(session)
    session["last_activity"] = datetime.now(timezone.utc).isoformat()
    await redis.setex(f"{SESSION_KEY_PREFIX}{session_id}", ttl, json.dumps(session))
    return session


async def destroy_session(redis: Any, session_id: str) -> None:
    if session_id:
        await redis.delete(f"{SESSION_KEY_PREFIX}{session_id}")


def session_user_public(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": session.get("user_id"),
        "email": session.get("email"),
        "nombre": session.get("nombre"),
        "rol": session.get("rol"),
        "initials": session.get("initials") or "",
    }
