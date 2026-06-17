"""Healthcheck CLI smoke tests."""

from __future__ import annotations

import subprocess
import sys


def test_healthcheck_cli_exits_nonzero_without_redis(monkeypatch) -> None:
    from duckclaw.cli.healthcheck import main

    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:6399/0")
    monkeypatch.setenv("DUCKCLAW_REDIS_URL", "redis://127.0.0.1:6399/0")
    assert main(["--redis-url", "redis://127.0.0.1:6399/0"]) == 1


def test_migrate_cli_verify_only_missing_db() -> None:
    from duckclaw.cli.migrate import main

    assert main(["--verify-only", "--db-path", "/no/such/hub.duckdb"]) == 1


def test_migrate_cli_module_invocation() -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "duckclaw.cli.migrate", "--verify-only", "--db-path", "/no/such/x.duckdb"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 1
