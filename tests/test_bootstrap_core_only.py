"""Bootstrap --core-only: esquema genérico sin dominios quant/finance."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest


def test_bootstrap_core_schema_creates_tables_no_domain_schemas(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "duckclaw.duckdb"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))

    from duckops.db_bootstrap import bootstrap_core_file

    bootstrap_core_file(db_path)

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        # agent_config lives in main catalog default schema
        assert con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = 'agent_config'"
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = 'api_conversation'"
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT count(*) FROM information_schema.tables WHERE table_name = 'telegram_conversation'"
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_name = 'semantic_memory'"
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_name = 'homeostasis_targets'"
        ).fetchone()[0] == 1
        assert con.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'harness_core'"
        ).fetchone()[0] == 0

        from duckclaw.bootstrap_core import core_unexpected_schemas_present

        assert core_unexpected_schemas_present(con, ("quant_core", "finance_worker", "harness_core")) == []
    finally:
        con.close()


def test_bootstrap_dbs_core_only_cli(tmp_path: Path, monkeypatch) -> None:
    repo = Path(__file__).resolve().parent.parent
    db_rel = "db/private/default/duckclaw.duckdb"
    db_path = repo / db_rel
    if db_path.is_file():
        db_path.unlink()
    monkeypatch.setenv("DUCKDB_PATH", db_rel)

    import subprocess

    r = subprocess.run(
        [
            "uv",
            "run",
            "duckops",
            "db",
            "bootstrap",
            "--core-only",
            "--only",
            db_rel,
        ],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stderr
    assert db_path.is_file()

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        from duckclaw.bootstrap_core import core_unexpected_schemas_present

        assert core_unexpected_schemas_present(con, ("quant_core", "finance_worker")) == []
    finally:
        con.close()
        db_path.unlink(missing_ok=True)


def test_bootstrap_default_templates_root_prefers_seed() -> None:
    from duckops.db_bootstrap import _default_templates_root

    root = _default_templates_root()
    assert root is not None
    assert root.name == "seed"
    assert (root / "default" / "manifest.yaml").is_file()


def test_sovereign_draft_default_vault_matches_session_db() -> None:
    from duckclaw.gateway_db import DEFAULT_SESSION_DB_RELPATH
    from duckops.sovereign.draft import SovereignDraft
    from duckops.sovereign.materialize import effective_primary_duckdb_relpath

    d = SovereignDraft()
    assert d.duckdb_vault_path == DEFAULT_SESSION_DB_RELPATH
    assert effective_primary_duckdb_relpath(d) == DEFAULT_SESSION_DB_RELPATH
