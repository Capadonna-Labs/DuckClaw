"""Smoke tests for the DuckClaw DuckDB bridge."""

from __future__ import annotations

import json

from duckclaw import DuckClaw


def test_duckclaw_in_memory_execute_and_query() -> None:
    db = DuckClaw(":memory:")
    db.execute("CREATE TABLE test (id INTEGER, name TEXT)")
    db.execute("INSERT INTO test VALUES (1, 'model-alpha'), (2, 'model-beta')")
    result = json.loads(db.query("SELECT * FROM test ORDER BY id"))
    assert result == [{"id": "1", "name": "model-alpha"}, {"id": "2", "name": "model-beta"}]
    assert db.get_version()
