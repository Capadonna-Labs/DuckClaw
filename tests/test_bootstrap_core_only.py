"""Bootstrap --core-only: esquema genérico sin dominios quant/pqrsd/finance."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest


def test_bootstrap_core_schema_creates_tables_no_domain_schemas(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "duckclaw.duckdb"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DUCKDB_PATH", str(db_path))

    from scripts.bootstrap_dbs import bootstrap_core_file

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

        from duckclaw.bootstrap_core import core_domain_schemas_present

        assert core_domain_schemas_present(con) == []
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
    import sys

    r = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts" / "bootstrap_dbs.py"),
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
        from duckclaw.bootstrap_core import core_domain_schemas_present

        assert core_domain_schemas_present(con) == []
    finally:
        con.close()
        db_path.unlink(missing_ok=True)
