from __future__ import annotations

from pathlib import Path

import pytest

from duckops.admin_bootstrap import (
    admin_bootstrap_ready,
    ensure_admin_env_merged,
    hydrate_draft_admin_from_repo,
    is_admin_key_valid,
    is_admin_password_valid,
    resolve_admin_env_updates,
    sync_admin_console_user_from_env,
)
from duckops.sovereign.draft import SovereignDraft
from duckops.sovereign.materialize import merge_env_file


def test_admin_password_rejects_placeholders() -> None:
    assert not is_admin_password_valid("change-me-min-8-chars")
    assert is_admin_password_valid("real-secret-1")


def test_admin_bootstrap_ready_key_or_password() -> None:
    assert admin_bootstrap_ready("a@b.c", "", "valid-non-placeholder-key-xyz")
    assert admin_bootstrap_ready("a@b.c", "long-enough", "")
    assert not admin_bootstrap_ready("a@b.c", "short", "")


def test_resolve_admin_env_generates_missing(tmp_path: Path) -> None:
    draft = SovereignDraft(admin_console_email="ops@test.local")
    updates = resolve_admin_env_updates(draft, tmp_path)
    assert updates["DUCKCLAW_ADMIN_EMAIL"] == "ops@test.local"
    assert is_admin_password_valid(updates["DUCKCLAW_ADMIN_PASSWORD"])
    assert is_admin_key_valid(updates["DUCKCLAW_ADMIN_API_KEY"])


def test_merge_env_idempotent_admin(tmp_path: Path) -> None:
    draft = SovereignDraft(admin_console_email="ops@test.local", admin_console_password="secret-pass-9")
    updates = resolve_admin_env_updates(draft, tmp_path, force_password=True)
    merge_env_file(tmp_path, updates)
    draft2 = SovereignDraft()
    hydrate_draft_admin_from_repo(tmp_path, draft2)
    updates2 = resolve_admin_env_updates(draft2, tmp_path)
    assert updates2["DUCKCLAW_ADMIN_PASSWORD"] == updates["DUCKCLAW_ADMIN_PASSWORD"]
    assert updates2["DUCKCLAW_ADMIN_API_KEY"] == updates["DUCKCLAW_ADMIN_API_KEY"]


def test_sync_admin_console_user_from_env_updates_existing(tmp_path: Path, monkeypatch) -> None:
    import duckdb

    from duckclaw.admin_console_users import authenticate_console_user, upsert_console_user

    db_path = tmp_path / "db" / "private" / "default" / "duckclaw.duckdb"
    db_path.parent.mkdir(parents=True)
    duckdb.connect(str(db_path)).close()

    (tmp_path / ".env").write_text(
        "DUCKCLAW_ADMIN_EMAIL=admin@duckclaw.local\n"
        "DUCKCLAW_ADMIN_PASSWORD=old-password-9\n"
        "DUCKCLAW_REPO_ROOT="
        + str(tmp_path).replace("\\", "/")
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "duckclaw.gateway_db.get_gateway_db_path",
        lambda: str(db_path),
    )

    con = duckdb.connect(str(db_path))
    try:
        upsert_console_user(
            con,
            email="admin@duckclaw.local",
            nombre="Administrador DuckClaw",
            rol="admin",
            password="old-password-9",
            initials="DC",
        )
    finally:
        con.close()

    (tmp_path / ".env").write_text(
        "DUCKCLAW_ADMIN_EMAIL=admin@duckclaw.local\n"
        "DUCKCLAW_ADMIN_PASSWORD=new-password-9\n"
        "DUCKCLAW_REPO_ROOT="
        + str(tmp_path).replace("\\", "/")
        + "\n",
        encoding="utf-8",
    )

    ok, detail = sync_admin_console_user_from_env(tmp_path)
    assert ok, detail
    assert detail == "admin@duckclaw.local"

    verify = duckdb.connect(str(db_path))
    try:
        user = authenticate_console_user(verify, email="admin@duckclaw.local", password="new-password-9")
        assert user is not None
    finally:
        verify.close()


def test_ensure_admin_env_merged_writes_admin_local(tmp_path: Path) -> None:
    admin_app = tmp_path / "apps" / "duckclaw-admin"
    admin_app.mkdir(parents=True)
    (admin_app / ".env.example").write_text(
        "DUCKCLAW_ADMIN_API_KEY=change-me-local-admin-key\n"
        "DUCKCLAW_ADMIN_EMAIL=admin@duckclaw.local\n",
        encoding="utf-8",
    )
    updates = ensure_admin_env_merged(tmp_path, gateway_url="http://127.0.0.1:8000")
    local = (admin_app / ".env.local").read_text(encoding="utf-8")
    assert updates["DUCKCLAW_ADMIN_API_KEY"] in local
    assert "http://127.0.0.1:8000" in local
