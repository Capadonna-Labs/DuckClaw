"""Hub conversation writes route through db-writer when Gateway is RO-only."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

_gw = Path(__file__).resolve().parents[1] / "services" / "api-gateway"
if str(_gw) not in sys.path:
    sys.path.insert(0, str(_gw))


@pytest.fixture()
def gateway_db(tmp_path, monkeypatch):
    db_path = tmp_path / "duckclaw.duckdb"
    monkeypatch.setenv("DUCKCLAW_GATEWAY_DB_PATH", str(db_path))
    monkeypatch.delenv("LITE_MODE", raising=False)
    monkeypatch.delenv("DUCKCLAW_SPAWN_PROFILE", raising=False)
    from duckclaw.schema_migrations import migrate_gateway_database

    migrate_gateway_database(str(db_path), seed_admin=False)
    return db_path


def test_save_messages_enqueues_one_batched_task(gateway_db, monkeypatch) -> None:
    """One task per save: each task costs the writer an exclusive RW lock on the hub."""
    import duckdb

    from core.admin_conversations_db import db_save_messages

    seen: list[str] = []

    monkeypatch.setattr(
        "core.admin_conversations_db._writes_via_db_writer",
        lambda: True,
    )
    monkeypatch.setattr(
        "duckclaw.db_write_queue.enqueue_duckdb_write_sync",
        lambda **kw: seen.append(str(kw.get("query") or "")) or "task-1",
    )

    db_save_messages(
        "default",
        "admin-conv-test",
        [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "ok"}],
    )

    assert len(seen) == 1
    query = seen[0]
    assert query.count("DELETE FROM main.admin_conversation_messages") == 1
    assert query.count("INSERT INTO main.admin_conversation_messages") == 2
    assert query.count("UPDATE main.admin_conversations") == 1

    # The writer sends the batch to DuckDB as a single execute(); it must be valid SQL.
    conn = duckdb.connect(str(gateway_db), read_only=False)
    try:
        conn.execute(query, [])
        rows = conn.execute(
            "SELECT role FROM main.admin_conversation_messages "
            "WHERE conversation_id = 'admin-conv-test' ORDER BY created_at"
        ).fetchall()
    finally:
        conn.close()
    assert [r[0] for r in rows] == ["user", "assistant"]
