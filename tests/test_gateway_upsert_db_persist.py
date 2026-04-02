"""Persistencia de DUCKCLAW_DB_PATH por bloque en api_gateways_pm2 (merge al upsert)."""

from __future__ import annotations

from duckclaw.ops.manager import _upsert_gateway_app


def test_upsert_preserves_db_path_when_incoming_env_differs() -> None:
    apps: list[dict] = [
        {
            "name": "Finanz-Gateway",
            "host": "0.0.0.0",
            "port": 8000,
            "env": {
                "DUCKCLAW_DB_PATH": "/vault/finanz.duckdb",
                "DUCKCLAW_SHARED_DB_PATH": "/shared/cat.duckdb",
                "DUCKDB_PATH": "/vault/finanz.duckdb",
                "FOO": "1",
            },
        }
    ]
    env_vars = {
        "DUCKCLAW_DB_PATH": "/other/jobhunter.duckdb",
        "PYTHONPATH": "/repo",
        "BAR": "2",
    }
    out = _upsert_gateway_app(
        apps,
        name="Finanz-Gateway",
        host="0.0.0.0",
        port=8000,
        env_vars=env_vars,
    )
    env = out[0]["env"]
    assert env["DUCKCLAW_DB_PATH"] == "/vault/finanz.duckdb"
    assert env["DUCKCLAW_SHARED_DB_PATH"] == "/shared/cat.duckdb"
    assert env["DUCKDB_PATH"] == "/vault/finanz.duckdb"
    assert env["BAR"] == "2"
    assert env["FOO"] == "1"


def test_upsert_forced_env_overrides_persisted_db_paths() -> None:
    apps: list[dict] = [
        {
            "name": "Finanz-Gateway",
            "host": "0.0.0.0",
            "port": 8000,
            "env": {"DUCKCLAW_DB_PATH": "/a/old.duckdb"},
        }
    ]
    env_vars = {"DUCKCLAW_DB_PATH": "/b/from_dotenv.duckdb"}
    out = _upsert_gateway_app(
        apps,
        name="Finanz-Gateway",
        host="0.0.0.0",
        port=8000,
        env_vars=env_vars,
        forced_env={"DUCKCLAW_DB_PATH": "/c/explicit.duckdb", "DUCKDB_PATH": "/c/explicit.duckdb"},
    )
    env = out[0]["env"]
    assert env["DUCKCLAW_DB_PATH"] == "/c/explicit.duckdb"
    assert env["DUCKDB_PATH"] == "/c/explicit.duckdb"


def test_upsert_new_gateway_uses_incoming_db_path() -> None:
    apps: list[dict] = []
    env_vars = {"DUCKCLAW_DB_PATH": "/x/brand_new.duckdb", "PYTHONPATH": "/repo"}
    out = _upsert_gateway_app(
        apps,
        name="New-Gateway",
        host="0.0.0.0",
        port=9000,
        env_vars=env_vars,
    )
    assert len(out) == 1
    assert out[0]["env"]["DUCKCLAW_DB_PATH"] == "/x/brand_new.duckdb"
    assert out[0]["port"] == 9000


def test_upsert_fills_empty_persisted_db_path_from_incoming() -> None:
    apps: list[dict] = [
        {
            "name": "Finanz-Gateway",
            "host": "0.0.0.0",
            "port": 8000,
            "env": {"DUCKCLAW_DB_PATH": ""},
        }
    ]
    out = _upsert_gateway_app(
        apps,
        name="Finanz-Gateway",
        host="0.0.0.0",
        port=8000,
        env_vars={"DUCKCLAW_DB_PATH": "/fill/in.duckdb"},
    )
    assert out[0]["env"]["DUCKCLAW_DB_PATH"] == "/fill/in.duckdb"
