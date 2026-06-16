"""Tests for verify_schema_integrity()."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest


def test_verify_schema_integrity_missing_db() -> None:
    from duckclaw.schema_migrations import verify_schema_integrity

    ok, message = verify_schema_integrity("/tmp/does-not-exist-duckclaw-migrate.duckdb")
    assert ok is False
    assert "duckclaw-migrate" in message


def test_verify_schema_integrity_after_migrate() -> None:
    from duckclaw.schema_migrations import migrate_gateway_database, verify_schema_integrity

    tmp = Path(tempfile.mkdtemp())
    db_path = str(tmp / "hub.duckdb")
    migrate_gateway_database(db_path, seed_admin=False)
    ok, message = verify_schema_integrity(db_path)
    assert ok is True
    assert message == "ok"


def test_verify_schema_integrity_strict_drift(monkeypatch) -> None:
    import duckdb

    from duckclaw.schema_migrations import (
        migrate_gateway_database,
        verify_migration_integrity,
        verify_schema_integrity,
    )

    tmp = Path(tempfile.mkdtemp())
    db_path = str(tmp / "strict.duckdb")
    migrate_gateway_database(db_path, seed_admin=False)
    monkeypatch.setenv("DUCKCLAW_SCHEMA_STRICT", "1")

    con = duckdb.connect(db_path)
    try:
        assert verify_migration_integrity(con) == []
    finally:
        con.close()

    con = duckdb.connect(db_path)
    try:
        con.execute("UPDATE main.schema_migrations SET checksum = 'bad' WHERE version = 1")
    finally:
        con.close()

    ok, message = verify_schema_integrity(db_path)
    assert ok is False
    assert "drift" in message.lower()


def test_migrate_gateway_database_idempotent() -> None:
    from duckclaw.schema_migrations import migrate_gateway_database

    tmp = Path(tempfile.mkdtemp())
    db_path = str(tmp / "idem.duckdb")
    first = migrate_gateway_database(db_path, seed_admin=False)
    second = migrate_gateway_database(db_path, seed_admin=False)
    assert len(first) >= 1
    assert second == []
