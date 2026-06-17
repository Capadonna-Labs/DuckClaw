from __future__ import annotations

from pathlib import Path


def test_run_framework_policy_preflight_ok_after_migrate(monkeypatch, tmp_path: Path) -> None:
    import duckdb

    from duckclaw.schema_migrations import run_pending_migrations
    from duckops.policy_health import run_framework_policy_preflight

    db_file = tmp_path / "hub.duckdb"
    con = duckdb.connect(str(db_file))
    run_pending_migrations(con)
    con.close()

    monkeypatch.setenv("DUCKCLAW_GATEWAY_DB_PATH", str(db_file))
    lines: list[str] = []

    ok = run_framework_policy_preflight(tmp_path, print_fn=lines.append, strict=False)

    assert ok is True
    assert any("framework policies activas" in line for line in lines)


def test_run_framework_policy_preflight_strict_fails_when_degraded(monkeypatch, tmp_path: Path) -> None:
    import duckdb

    from duckclaw.schema_migrations import run_pending_migrations
    from duckops.policy_health import run_framework_policy_preflight

    db_file = tmp_path / "hub.duckdb"
    con = duckdb.connect(str(db_file))
    run_pending_migrations(con)
    con.execute("DELETE FROM main.prompt_policy_registry")
    con.close()

    monkeypatch.setenv("DUCKCLAW_GATEWAY_DB_PATH", str(db_file))
    lines: list[str] = []

    ok = run_framework_policy_preflight(tmp_path, print_fn=lines.append, strict=True)

    assert ok is False
    assert any("degradado (--strict)" in line for line in lines)


def test_run_framework_policy_preflight_warns_degraded_without_strict(
    monkeypatch, tmp_path: Path,
) -> None:
    import duckdb

    from duckclaw.schema_migrations import run_pending_migrations
    from duckops.policy_health import run_framework_policy_preflight

    db_file = tmp_path / "hub.duckdb"
    con = duckdb.connect(str(db_file))
    run_pending_migrations(con)
    con.execute("DELETE FROM main.prompt_policy_registry")
    con.close()

    monkeypatch.setenv("DUCKCLAW_GATEWAY_DB_PATH", str(db_file))
    lines: list[str] = []

    ok = run_framework_policy_preflight(tmp_path, print_fn=lines.append, strict=False)

    assert ok is True
    assert any("degradado capa 0" in line for line in lines)
