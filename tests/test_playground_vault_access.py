"""Playground admin: bóveda por defecto alineada con hub gateway (RAG)."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from gateway_import import ensure_gateway_on_sys_path


@pytest.fixture
def playground_vault_mod():
    ensure_gateway_on_sys_path()
    from routers.admin_domains.playground import vault_access as mod

    return mod


def test_playground_vault_db_path_defaults_to_gateway_hub(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    playground_vault_mod,
) -> None:
    repo = tmp_path / "repo"
    (repo / "db").mkdir(parents=True)
    hub = repo / "db" / "hub.duckdb"
    hub.touch()
    private_vault = repo / "db" / "private" / "user123" / "active.duckdb"
    private_vault.parent.mkdir(parents=True)
    private_vault.touch()

    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo))
    monkeypatch.setenv("DUCKCLAW_GATEWAY_DB_PATH", "db/hub.duckdb")
    monkeypatch.setattr(
        "duckclaw.vaults.resolve_active_vault",
        lambda _uid, _scope: ("active", str(private_vault)),
    )

    team_ctx = {"tenant_id": "default", "telegram_user_id": "user123"}
    result = playground_vault_mod.playground_vault_db_path(team_ctx, worker_id="default")
    assert Path(result).resolve() == hub.resolve()


def test_playground_vault_db_path_falls_back_when_hub_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    playground_vault_mod,
) -> None:
    repo = tmp_path / "repo"
    private_vault = repo / "db" / "private" / "user123" / "active.duckdb"
    private_vault.parent.mkdir(parents=True)
    private_vault.touch()

    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo))
    monkeypatch.setenv("DUCKCLAW_GATEWAY_DB_PATH", "db/missing-hub.duckdb")
    monkeypatch.setattr(
        "duckclaw.vaults.resolve_active_vault",
        lambda _uid, _scope: ("active", str(private_vault)),
    )

    team_ctx = {"tenant_id": "default", "telegram_user_id": "user123"}
    result = playground_vault_mod.playground_vault_db_path(team_ctx, worker_id="default")
    assert Path(result).resolve() == private_vault.resolve()


def test_resolved_vault_for_admin_chat_default_matches_gateway(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    playground_vault_mod,
) -> None:
    repo = tmp_path / "repo"
    (repo / "db").mkdir(parents=True)
    hub = repo / "db" / "hub.duckdb"
    hub.touch()

    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo))
    monkeypatch.setenv("DUCKCLAW_GATEWAY_DB_PATH", "db/hub.duckdb")

    team_ctx = {"tenant_id": "default", "telegram_user_id": "user123"}
    vault = asyncio.run(
        playground_vault_mod.resolved_vault_for_admin_chat(
            "admin-playground",
            team_ctx,
            "default",
        )
    )
    assert Path(vault["effective_path"]).resolve() == hub.resolve()
    assert Path(vault["default_path"]).resolve() == hub.resolve()
    assert vault["scope"] == "default"
    assert vault["override_path"] is None


def test_resolved_vault_for_admin_chat_body_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    playground_vault_mod,
) -> None:
    repo = tmp_path / "repo"
    (repo / "db").mkdir(parents=True)
    hub = repo / "db" / "hub.duckdb"
    hub.touch()
    alt = repo / "db" / "alt.duckdb"
    alt.touch()

    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(repo))
    monkeypatch.setenv("DUCKCLAW_GATEWAY_DB_PATH", "db/hub.duckdb")

    team_ctx = {"tenant_id": "default", "telegram_user_id": "user123"}
    vault = asyncio.run(
        playground_vault_mod.resolved_vault_for_admin_chat(
            "admin-playground",
            team_ctx,
            "default",
            body_override=str(alt),
        )
    )
    assert Path(vault["effective_path"]).resolve() == alt.resolve()
    assert Path(vault["default_path"]).resolve() == hub.resolve()
    assert vault["scope"] == "chat"
    assert Path(vault["override_path"]).resolve() == alt.resolve()
