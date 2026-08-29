"""Catalog load must fall back to hub when vault has empty admin_worker_catalog."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from duckclaw.admin_user_profiles import ensure_profile_for_user
from duckclaw.admin_worker_catalog import (
    add_worker_version,
    create_worker,
    ensure_admin_worker_catalog_schema,
)
from duckclaw.bootstrap_core import bootstrap_core_schema
from duckclaw.catalog_worker import load_manifest_from_catalog
from duckclaw.gateway_db import GatewayDbEphemeralReadonly


class _Adapter:
    def __init__(self, con: duckdb.DuckDBPyConnection, path: str = "") -> None:
        self._con = con
        self._path = path
        self._read_only = False

    def execute(self, sql: str, params=None):
        if params is not None:
            return self._con.execute(sql, params)
        return self._con.execute(sql)


def test_catalog_worker_id_variants_hyphen_underscore() -> None:
    from duckclaw.admin_worker_catalog import catalog_worker_id_variants

    assert catalog_worker_id_variants("quant_reporter") == (
        "quant_reporter",
        "quant-reporter",
    )
    assert catalog_worker_id_variants("quant-reporter") == (
        "quant-reporter",
        "quant_reporter",
    )


def test_get_worker_by_tenant_worker_id_resolves_underscore_alias(
    tmp_path: Path,
) -> None:
    from duckclaw.admin_worker_catalog import create_worker, get_worker_by_tenant_worker_id

    db_path = tmp_path / "hub.duckdb"
    con = duckdb.connect(str(db_path))
    try:
        bootstrap_core_schema(con)
        ensure_admin_worker_catalog_schema(con)
        profile = ensure_profile_for_user(con, email="owner@test.com")
        create_worker(
            con,
            owner_email="owner@test.com",
            worker_id="quant-reporter",
            display_name="Quant Reporter",
            source_kind="template_import",
        )
        row = get_worker_by_tenant_worker_id(
            con, tenant_id=profile["tenant_id"], worker_id="quant_reporter"
        )
        assert row is not None
        assert row["worker_id"] == "quant-reporter"
    finally:
        con.close()


def test_load_manifest_falls_back_to_hub_when_vault_catalog_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    hub_path = tmp_path / "hub.duckdb"
    vault_path = tmp_path / "vault.duckdb"
    hub_con = duckdb.connect(str(hub_path))
    vault_con = duckdb.connect(str(vault_path))
    try:
        hub = _Adapter(hub_con, str(hub_path))
        vault = _Adapter(vault_con, str(vault_path))
        bootstrap_core_schema(hub, seed_admin=False)
        profile = ensure_profile_for_user(hub, email="qt@test.local")
        worker = create_worker(
            hub,
            owner_email=profile["email"],
            worker_id="demo-worker",
            display_name="Demo Worker",
        )
        add_worker_version(
            hub,
            worker_uid=worker["worker_uid"],
            created_by=profile["email"],
            manifest_snapshot={"id": "demo-worker", "skills": []},
            files_snapshot={"manifest.yaml": "id: demo-worker\nskills: []\n"},
            change_note="test",
        )
        ensure_admin_worker_catalog_schema(vault)
        assert (
            vault_con.execute("SELECT count(*) FROM main.admin_worker_catalog").fetchone()[0]
            == 0
        )

        # Release RW lock so hub RO fallback can open the same file.
        hub_con.close()
        monkeypatch.setenv("DUCKCLAW_GATEWAY_DB_PATH", str(hub_path))
        import duckclaw.catalog_worker as cw

        monkeypatch.setattr(
            cw,
            "_hub_catalog_db_if_different",
            lambda _db: GatewayDbEphemeralReadonly(str(hub_path)),
        )

        spec = load_manifest_from_catalog(
            vault, "demo-worker", tenant_id=profile["tenant_id"]
        )
        assert getattr(spec, "worker_id", None) == "demo-worker"
    finally:
        try:
            hub_con.close()
        except Exception:
            pass
        vault_con.close()
