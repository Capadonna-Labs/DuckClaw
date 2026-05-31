"""
Usuarios de la consola web (duckclaw-admin) en el hub DuckDB del gateway.

Spec: specs/features/platform/ADMIN_ACCESS_MANAGEMENT.md
Auth crypto: specs/features/platform/ADMIN_CONSOLE_AUTH.md
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
from datetime import datetime, timezone
from typing import Any, Optional

from duckclaw.shared_db_grants import _query_all_dicts, _sql_lit

_ADMIN_CONSOLE_USERS_DDL = """
CREATE TABLE IF NOT EXISTS main.admin_console_users (
    email VARCHAR PRIMARY KEY,
    nombre VARCHAR NOT NULL,
    rol VARCHAR NOT NULL DEFAULT 'viewer',
    password_hash VARCHAR NOT NULL,
    initials VARCHAR,
    active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_PBKDF2_ITERATIONS = max(200_000, int(os.environ.get("PBKDF2_ITERATIONS", "260000")))
_HASH_PREFIX = "pbkdf2_sha256"

_AUTH_COLUMN_MIGRATIONS = [
    "ALTER TABLE main.admin_console_users ADD COLUMN IF NOT EXISTS hash_algo TEXT DEFAULT 'pbkdf2_sha256'",
    "ALTER TABLE main.admin_console_users ADD COLUMN IF NOT EXISTS hash_params JSON",
    "ALTER TABLE main.admin_console_users ADD COLUMN IF NOT EXISTS failed_login_count INTEGER DEFAULT 0",
    "ALTER TABLE main.admin_console_users ADD COLUMN IF NOT EXISTS last_failed_at TIMESTAMP",
]


def ensure_admin_auth_columns(db: Any) -> None:
    if getattr(db, "_read_only", False):
        return
    for stmt in _AUTH_COLUMN_MIGRATIONS:
        db.execute(stmt)


def ensure_admin_console_users_table(db: Any) -> None:
    if getattr(db, "_read_only", False):
        return
    db.execute(_ADMIN_CONSOLE_USERS_DDL)
    ensure_admin_auth_columns(db)


def hash_password(plain: str) -> str:
    """New passwords: Argon2id."""
    from duckclaw.admin_auth_crypto import hash_password_argon2

    hashed, _, _ = hash_password_argon2(plain)
    return hashed


def hash_password_with_meta(plain: str) -> tuple[str, str, dict[str, int]]:
    from duckclaw.admin_auth_crypto import hash_password_argon2

    return hash_password_argon2(plain)


def verify_password(plain: str, stored_hash: str) -> bool:
    raw = (stored_hash or "").strip()
    if not raw.startswith(f"{_HASH_PREFIX}$"):
        return False
    parts = raw.split("$")
    if len(parts) != 4:
        return False
    try:
        iterations = int(parts[1])
        salt = base64.b64decode(parts[2])
        expected = base64.b64decode(parts[3])
    except (ValueError, TypeError):
        return False
    got = hashlib.pbkdf2_hmac("sha256", (plain or "").encode("utf-8"), salt, iterations)
    return secrets.compare_digest(got, expected)


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _row_to_public(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "email": str(row.get("email") or ""),
        "nombre": str(row.get("nombre") or ""),
        "rol": str(row.get("rol") or "viewer"),
        "initials": str(row.get("initials") or ""),
        "active": bool(row.get("active", True)),
        "created_at": str(row.get("created_at") or ""),
        "updated_at": str(row.get("updated_at") or ""),
    }


def list_console_users(db: Any, *, include_inactive: bool = True) -> list[dict[str, Any]]:
    ensure_admin_console_users_table(db)
    where = "" if include_inactive else " WHERE active = true"
    rows = _query_all_dicts(
        db,
        f"SELECT email, nombre, rol, initials, active, created_at, updated_at "
        f"FROM main.admin_console_users{where} ORDER BY email",
    )
    return [_row_to_public(r) for r in rows if isinstance(r, dict)]


def count_console_users(db: Any) -> int:
    ensure_admin_console_users_table(db)
    rows = _query_all_dicts(db, "SELECT COUNT(*) AS n FROM main.admin_console_users")
    if rows and isinstance(rows[0], dict):
        return int(rows[0].get("n") or 0)
    return 0


def get_by_email(db: Any, email: str) -> Optional[dict[str, Any]]:
    ensure_admin_console_users_table(db)
    em = _sql_lit(_normalize_email(email), 256)
    rows = _query_all_dicts(
        db,
        f"SELECT email, nombre, rol, password_hash, hash_algo, hash_params, "
        f"failed_login_count, last_failed_at, initials, active, created_at, updated_at "
        f"FROM main.admin_console_users WHERE email = '{em}' LIMIT 1",
    )
    if not rows or not isinstance(rows[0], dict):
        return None
    return dict(rows[0])


def _update_password_hash(
    db: Any,
    email: str,
    password_hash: str,
    hash_algo: str,
    hash_params: dict[str, int],
) -> None:
    em_sql = _sql_lit(_normalize_email(email), 256)
    pwd_sql = _sql_lit(password_hash, 1024)
    algo_sql = _sql_lit(hash_algo, 32)
    params_sql = _sql_lit(json.dumps(hash_params), 512)
    db.execute(
        f"""
        UPDATE main.admin_console_users SET
          password_hash = '{pwd_sql}',
          hash_algo = '{algo_sql}',
          hash_params = '{params_sql}'::JSON,
          failed_login_count = 0,
          last_failed_at = NULL,
          updated_at = CURRENT_TIMESTAMP
        WHERE email = '{em_sql}'
        """
    )


def record_login_failure(db: Any, email: str) -> int:
    ensure_admin_console_users_table(db)
    em_sql = _sql_lit(_normalize_email(email), 256)
    db.execute(
        f"""
        UPDATE main.admin_console_users SET
          failed_login_count = COALESCE(failed_login_count, 0) + 1,
          last_failed_at = CURRENT_TIMESTAMP,
          updated_at = CURRENT_TIMESTAMP
        WHERE email = '{em_sql}'
        """
    )
    row = get_by_email(db, email)
    return int(row.get("failed_login_count") or 0) if row else 0


def clear_login_failures(db: Any, email: str) -> None:
    ensure_admin_console_users_table(db)
    em_sql = _sql_lit(_normalize_email(email), 256)
    db.execute(
        f"""
        UPDATE main.admin_console_users SET
          failed_login_count = 0,
          last_failed_at = NULL,
          updated_at = CURRENT_TIMESTAMP
        WHERE email = '{em_sql}'
        """
    )


def authenticate_console_user(db: Any, *, email: str, password: str) -> Optional[dict[str, Any]]:
    from duckclaw.admin_auth_crypto import verify_and_migrate

    row = get_by_email(db, email)
    if not row or not row.get("active", True):
        return None

    def _db_update(em: str, pwd_hash: str, algo: str, params: dict[str, int]) -> None:
        _update_password_hash(db, em, pwd_hash, algo, params)

    if not verify_and_migrate(email, password, row, _db_update):
        return None
    clear_login_failures(db, email)
    pub = _row_to_public(row)
    pub["id"] = f"user-{pub['email']}"
    return pub


def upsert_console_user(
    db: Any,
    *,
    email: str,
    nombre: str,
    rol: str,
    password: str | None = None,
    initials: str = "",
    active: bool = True,
) -> dict[str, Any]:
    ensure_admin_console_users_table(db)
    em = _normalize_email(email)
    if not em:
        raise ValueError("email requerido")
    role = (rol or "user").strip().lower()
    if role == "viewer":
        role = "user"
    if role not in ("admin", "user"):
        raise ValueError("rol inválido")
    existing = get_by_email(db, em)
    pwd_hash: str | None = None
    pwd_algo = "argon2id"
    pwd_params: dict[str, int] | None = None
    if password:
        pwd_hash, pwd_algo, pwd_params = hash_password_with_meta(password)
    if existing is None and not pwd_hash:
        raise ValueError("password requerido para usuario nuevo")
    em_sql = _sql_lit(em, 256)
    nombre_sql = _sql_lit((nombre or em).strip(), 256)
    role_sql = _sql_lit(role, 32)
    initials_sql = _sql_lit((initials or em[:2]).upper()[:8], 16)
    active_sql = "true" if active else "false"
    if existing is None:
        assert pwd_hash is not None and pwd_params is not None
        pwd_sql = _sql_lit(pwd_hash, 1024)
        algo_sql = _sql_lit(pwd_algo, 32)
        params_sql = _sql_lit(json.dumps(pwd_params), 512)
        db.execute(
            f"""
            INSERT INTO main.admin_console_users
              (email, nombre, rol, password_hash, hash_algo, hash_params, initials, active)
            VALUES (
              '{em_sql}', '{nombre_sql}', '{role_sql}', '{pwd_sql}',
              '{algo_sql}', '{params_sql}'::JSON, '{initials_sql}', {active_sql}
            )
            """
        )
    else:
        pwd_clause = ""
        if pwd_hash and pwd_params is not None:
            pwd_clause = (
                f", password_hash = '{_sql_lit(pwd_hash, 1024)}'"
                f", hash_algo = '{_sql_lit(pwd_algo, 32)}'"
                f", hash_params = '{_sql_lit(json.dumps(pwd_params), 512)}'::JSON"
            )
        db.execute(
            f"""
            UPDATE main.admin_console_users SET
              nombre = '{nombre_sql}',
              rol = '{role_sql}',
              initials = '{initials_sql}',
              active = {active_sql},
              updated_at = CURRENT_TIMESTAMP
              {pwd_clause}
            WHERE email = '{em_sql}'
            """
        )
    row = get_by_email(db, em)
    if not row:
        raise RuntimeError("upsert failed")
    return _row_to_public(row)


def deactivate_console_user(db: Any, *, email: str) -> bool:
    ensure_admin_console_users_table(db)
    em_sql = _sql_lit(_normalize_email(email), 256)
    before = get_by_email(db, email)
    if not before:
        return False
    db.execute(
        f"""
        UPDATE main.admin_console_users SET active = false, updated_at = CURRENT_TIMESTAMP
        WHERE email = '{em_sql}'
        """
    )
    return True


def default_seed_users() -> list[dict[str, str]]:
    """Seed from env only — no hardcoded passwords in source."""
    email = (os.environ.get("DUCKCLAW_ADMIN_EMAIL") or "admin@duckclaw.local").strip()
    password = (os.environ.get("DUCKCLAW_ADMIN_PASSWORD") or "").strip()
    if not password:
        password = secrets.token_urlsafe(16)
    users: list[dict[str, str]] = [
        {
            "email": email,
            "nombre": "Administrador DuckClaw",
            "rol": "admin",
            "password": password,
            "initials": "DC",
        }
    ]
    user_email = (os.environ.get("DUCKCLAW_USER_EMAIL") or "").strip()
    user_password = (os.environ.get("DUCKCLAW_USER_PASSWORD") or "").strip()
    if user_email and user_password:
        users.append(
            {
                "email": user_email,
                "nombre": "Usuario DuckClaw",
                "rol": "user",
                "password": user_password,
                "initials": "UD",
            }
        )
    return users


def seed_admin_console_users_if_empty(db: Any, users: list[dict[str, str]] | None = None) -> int:
    """Inserta usuarios seed si la tabla está vacía. Retorna cantidad insertada."""
    ensure_admin_console_users_table(db)
    if count_console_users(db) > 0:
        return 0
    inserted = 0
    for u in users or default_seed_users():
        upsert_console_user(
            db,
            email=u["email"],
            nombre=u.get("nombre") or u["email"],
            rol=u.get("rol") or "user",
            password=u.get("password") or "",
            initials=u.get("initials") or "",
            active=True,
        )
        inserted += 1
    return inserted
