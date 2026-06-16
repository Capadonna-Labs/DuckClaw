"""Admin console user and login-state typed write handlers."""
from __future__ import annotations

from typing import Any


def _apply_upsert_console_user(conn: Any, payload: dict) -> None:
    from duckclaw.admin_console_users import upsert_console_user

    upsert_console_user(
        conn,
        email=str(payload.get("email") or ""),
        nombre=str(payload.get("nombre") or ""),
        rol=str(payload.get("rol") or "user"),
        password=payload.get("password"),
        initials=str(payload.get("initials") or ""),
        active=bool(payload.get("active", True)),
    )


def _apply_deactivate_console_user(conn: Any, payload: dict) -> None:
    from duckclaw.admin_console_users import deactivate_console_user

    email = str(payload.get("email") or "").strip()
    if not email:
        raise ValueError("email required")
    ok = deactivate_console_user(conn, email=email)
    if not ok:
        raise ValueError(f"Console user not found: {email}")


def _apply_record_admin_login_failure(conn: Any, payload: dict) -> None:
    from duckclaw.admin_console_users import record_login_failure

    email = str(payload.get("email") or "").strip()
    if not email:
        raise ValueError("email required")
    record_login_failure(conn, email)


def _apply_clear_admin_login_failures(conn: Any, payload: dict) -> None:
    from duckclaw.admin_console_users import clear_login_failures

    email = str(payload.get("email") or "").strip()
    if not email:
        raise ValueError("email required")
    clear_login_failures(conn, email)


def _apply_update_console_user_password_hash(conn: Any, payload: dict) -> None:
    from duckclaw.admin_console_users import update_console_user_password_hash

    email = str(payload.get("email") or "").strip()
    password_hash = str(payload.get("password_hash") or "").strip()
    hash_algo = str(payload.get("hash_algo") or "argon2id").strip()
    hash_params = payload.get("hash_params")
    if not email:
        raise ValueError("email required")
    if not password_hash:
        raise ValueError("password_hash required")
    if not isinstance(hash_params, dict):
        hash_params = {}
    update_console_user_password_hash(
        conn,
        email=email,
        password_hash=password_hash,
        hash_algo=hash_algo,
        hash_params=hash_params,
    )
