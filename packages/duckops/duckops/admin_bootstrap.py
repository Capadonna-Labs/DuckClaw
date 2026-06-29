"""Bootstrap consola admin: claves .env y sync con apps/duckclaw-admin/.env.local."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from duckops.sovereign.draft import SovereignDraft

PLACEHOLDER_ADMIN_KEYS = frozenset({"", "change-me-local-admin-key", "change-me"})
PLACEHOLDER_ADMIN_PASSWORDS = frozenset(
    {"", "change-me", "change-me-min-8-chars", "changeme", "password"}
)

ADMIN_ENV_KEYS = (
    "DUCKCLAW_ADMIN_EMAIL",
    "DUCKCLAW_ADMIN_PASSWORD",
    "DUCKCLAW_ADMIN_API_KEY",
)


def generate_admin_api_key() -> str:
    return secrets.token_urlsafe(32)


def generate_admin_password() -> str:
    return secrets.token_urlsafe(12)


def is_admin_key_valid(key: str | None) -> bool:
    return bool((key or "").strip()) and (key or "").strip() not in PLACEHOLDER_ADMIN_KEYS


def is_admin_password_valid(password: str | None) -> bool:
    p = (password or "").strip()
    return len(p) >= 8 and p not in PLACEHOLDER_ADMIN_PASSWORDS


def admin_bootstrap_ready(email: str | None, password: str | None, api_key: str | None) -> bool:
    if is_admin_key_valid(api_key):
        return True
    return bool((email or "").strip()) and is_admin_password_valid(password)


def _flat_env(repo_root: Path) -> dict[str, str]:
    from duckclaw.dotenv_immutable import merged_root_and_proposed_flat_env

    return merged_root_and_proposed_flat_env(repo_root)


def _duckdb_adapter(con: Any) -> Any:
    """Adaptador DuckDB: ``execute`` debe devolver el cursor para SELECT/upsert."""

    class _Adapter:
        def execute(self, sql: str, params: list | None = None) -> Any:
            if params:
                return con.execute(sql, params)
            return con.execute(sql)

    return _Adapter()


def hydrate_draft_admin_from_repo(repo_root: Path, draft: SovereignDraft) -> None:
    """Rellena el borrador desde .env existente (re-run idempotente)."""
    env = _flat_env(repo_root)
    email = (env.get("DUCKCLAW_ADMIN_EMAIL") or draft.admin_console_email or "admin@duckclaw.local").strip()
    password = (env.get("DUCKCLAW_ADMIN_PASSWORD") or draft.admin_console_password or "").strip()
    api_key = (env.get("DUCKCLAW_ADMIN_API_KEY") or draft.admin_api_key or "").strip()
    draft.admin_console_email = email
    if is_admin_password_valid(password):
        draft.admin_console_password = password
    if is_admin_key_valid(api_key):
        draft.admin_api_key = api_key


def resolve_admin_env_updates(
    draft: SovereignDraft,
    repo_root: Path,
    *,
    force_password: bool = False,
) -> dict[str, str]:
    """
    Calcula claves admin para merge en .env.

    Conserva valores existentes válidos; genera password/key si faltan o son placeholder.
    """
    env = _flat_env(repo_root)
    email = (draft.admin_console_email or env.get("DUCKCLAW_ADMIN_EMAIL") or "admin@duckclaw.local").strip()
    password = (draft.admin_console_password or "").strip()
    if not is_admin_password_valid(password):
        existing_pw = (env.get("DUCKCLAW_ADMIN_PASSWORD") or "").strip()
        if not force_password and is_admin_password_valid(existing_pw):
            password = existing_pw
        else:
            password = generate_admin_password()
            draft.admin_console_password = password
            draft.admin_password_auto_generated = True

    api_key = (draft.admin_api_key or "").strip()
    if not is_admin_key_valid(api_key):
        existing_key = (env.get("DUCKCLAW_ADMIN_API_KEY") or "").strip()
        if is_admin_key_valid(existing_key):
            api_key = existing_key
        else:
            api_key = generate_admin_api_key()
            draft.admin_api_key = api_key

    draft.admin_console_email = email
    return {
        "DUCKCLAW_ADMIN_EMAIL": email,
        "DUCKCLAW_ADMIN_PASSWORD": password,
        "DUCKCLAW_ADMIN_API_KEY": api_key,
    }


def merge_admin_env_local(repo_root: Path, updates: dict[str, str], *, gateway_url: str = "") -> None:
    """Fusiona claves admin (+ gateway URL) en apps/duckclaw-admin/.env.local."""
    from duckops.sovereign.atomic import atomic_write

    admin_dir = repo_root / "apps" / "duckclaw-admin"
    if not admin_dir.is_dir():
        return
    target = admin_dir / ".env.local"
    example = admin_dir / ".env.example"
    if not target.is_file() and example.is_file():
        target.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")

    keys_done: set[str] = set()
    new_lines: list[str] = []
    if target.is_file():
        for line in target.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in line:
                new_lines.append(line)
                continue
            k, _, _ = line.partition("=")
            k = k.strip()
            if k in updates:
                new_lines.append(f"{k}={updates[k]}")
                keys_done.add(k)
            elif k == "DUCKCLAW_GATEWAY_URL" and gateway_url:
                new_lines.append(f"DUCKCLAW_GATEWAY_URL={gateway_url}")
                keys_done.add(k)
            else:
                new_lines.append(line)
    for key in ADMIN_ENV_KEYS:
        if key in updates and key not in keys_done:
            new_lines.append(f"{key}={updates[key]}")
    if gateway_url and "DUCKCLAW_GATEWAY_URL" not in keys_done:
        new_lines.append(f"DUCKCLAW_GATEWAY_URL={gateway_url}")
    atomic_write(target, "\n".join(new_lines) + "\n", encoding="utf-8")


def seed_admin_console_users(repo_root: Path, db_rel_path: str, draft: SovereignDraft) -> int:
    """Inserta usuario admin si la tabla está vacía (idempotente)."""
    import duckdb

    from duckclaw.admin_console_users import seed_admin_console_users_if_empty

    db_path = Path(db_rel_path)
    if not db_path.is_absolute():
        db_path = (repo_root / db_path).resolve()
    if not db_path.is_file():
        return 0

    email = (draft.admin_console_email or "admin@duckclaw.local").strip()
    password = (draft.admin_console_password or "").strip()
    if not is_admin_password_valid(password):
        return 0

    users = [
        {
            "email": email,
            "nombre": "Administrador DuckClaw",
            "rol": "admin",
            "password": password,
            "initials": "DC",
        }
    ]
    con = duckdb.connect(str(db_path), read_only=False)
    try:
        return seed_admin_console_users_if_empty(_duckdb_adapter(con), users)
    finally:
        con.close()


def sync_admin_console_user_from_env(
    repo_root: Path,
    db_path: str | Path | None = None,
) -> tuple[bool, str]:
    """Upsert admin console user from DUCKCLAW_ADMIN_EMAIL/PASSWORD when credentials are valid."""
    import duckdb

    from duckclaw.admin_console_users import upsert_console_user
    from duckclaw.gateway_db import get_gateway_db_path

    env = _flat_env(repo_root)
    email = (env.get("DUCKCLAW_ADMIN_EMAIL") or "").strip()
    password = (env.get("DUCKCLAW_ADMIN_PASSWORD") or "").strip()
    api_key = (env.get("DUCKCLAW_ADMIN_API_KEY") or "").strip()
    if not admin_bootstrap_ready(email, password, api_key):
        return False, "credenciales .env incompletas o placeholder"

    resolved = Path(db_path) if db_path else Path((get_gateway_db_path() or "").strip())
    if not resolved.is_absolute():
        resolved = (repo_root / resolved).resolve()
    if not resolved.is_file():
        return False, f"bóveda ausente: {resolved}"

    con = duckdb.connect(str(resolved), read_only=False)
    try:
        upsert_console_user(
            _duckdb_adapter(con),
            email=email,
            nombre="Administrador DuckClaw",
            rol="admin",
            password=password,
            initials="DC",
            active=True,
        )
    finally:
        con.close()
    return True, email


def ensure_admin_env_merged(
    repo_root: Path,
    draft: SovereignDraft | None = None,
    *,
    gateway_url: str = "",
) -> dict[str, str]:
    """
    Asegura claves admin en .env (y .env.local del admin) sin TUI.

    Útil tras wizard clásico o re-run no interactivo.
    """
    from duckops.sovereign.draft import SovereignDraft as Draft
    from duckops.sovereign.materialize import merge_env_file

    working: SovereignDraft = draft if draft is not None else Draft()
    hydrate_draft_admin_from_repo(repo_root, working)
    updates = resolve_admin_env_updates(working, repo_root)
    merge_env_file(repo_root, updates)
    merge_admin_env_local(repo_root, updates, gateway_url=gateway_url)
    return updates
