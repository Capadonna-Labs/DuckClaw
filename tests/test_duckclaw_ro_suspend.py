"""DuckClaw: suspender conexión RO y reanudar (handoff de lock hacia db-writer)."""

from pathlib import Path

import duckclaw


def test_suspend_resume_readonly_reopens(tmp_path: Path) -> None:
    p = tmp_path / "vault.duckdb"
    w = duckclaw.DuckClaw(str(p), read_only=False)
    w.execute("CREATE TABLE t1(x INTEGER)")
    w.close()

    r = duckclaw.DuckClaw(str(p), read_only=True)
    assert '"x"' in r.query("PRAGMA table_info('t1')") or "t1" in r.query("SHOW TABLES")
    r.suspend_readonly_file_handle()
    assert r._con is None
    r.resume_readonly_file_handle()
    out = r.query("SELECT 1 AS n")
    assert "1" in out
    r.close()
