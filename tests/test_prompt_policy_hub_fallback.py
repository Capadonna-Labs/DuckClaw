"""Playground vaults have no prompt_policy_registry; policies are read from the hub."""

from __future__ import annotations

import duckdb


class _VaultDb:
    def __init__(self, path: str, *, missing: bool, inner=None) -> None:
        self._path = path
        self._missing = missing
        self._inner = inner

    def execute(self, sql: str, params=None):
        if self._missing:
            raise duckdb.CatalogException(
                "Catalog Error: Table with name prompt_policy_registry does not exist!"
            )
        if params is None:
            return self._inner.execute(sql)
        return self._inner.execute(sql, params)


def test_vault_without_registry_resolves_rag_turn_from_hub(monkeypatch, tmp_path) -> None:
    from duckclaw.prompt_policies.resolver import (
        PromptPolicyResolver,
        prompt_policy_source_db,
    )
    from duckclaw.schema_migrations import run_pending_migrations

    hub_path = tmp_path / "hub.duckdb"
    vault_path = tmp_path / "playground.duckdb"
    vault_path.write_bytes(b"")
    hub = duckdb.connect(str(hub_path))
    run_pending_migrations(hub)
    hub.execute(
        "UPDATE main.prompt_policy_registry SET content = ? "
        "WHERE policy_type = 'system_prompt' AND policy_name = 'default' AND active = true",
        ["hub default for {worker_id}"],
    )
    hub.close()

    monkeypatch.setattr(
        "duckclaw.prompt_policies.resolver.get_gateway_db_path",
        lambda: str(hub_path),
    )
    source = prompt_policy_source_db(_VaultDb(str(vault_path), missing=True))
    prompt = PromptPolicyResolver(db=source).load("system_prompt", "rag_turn")
    writer = duckdb.connect(str(hub_path))
    writer.close()

    assert "hub default" in prompt


def test_vault_with_registry_stays_on_the_vault(tmp_path) -> None:
    from duckclaw.prompt_policies.resolver import prompt_policy_source_db
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    vault = _VaultDb(str(tmp_path / "vault.duckdb"), missing=False, inner=con)
    assert prompt_policy_source_db(vault) is vault
    con.close()


def test_unmigrated_hub_file_is_not_swapped(monkeypatch, tmp_path) -> None:
    from duckclaw.prompt_policies.resolver import prompt_policy_source_db

    hub_path = tmp_path / "hub.duckdb"
    hub_path.write_bytes(b"")
    monkeypatch.setattr(
        "duckclaw.prompt_policies.resolver.get_gateway_db_path",
        lambda: str(hub_path),
    )
    vault = _VaultDb(str(hub_path), missing=True)
    assert prompt_policy_source_db(vault) is vault
