from __future__ import annotations

import duckdb

from duckclaw.commands.suggestions_auto import (
    SUGGESTIONS_AUTO_KEY,
    set_suggestions_auto_enabled,
    suggestions_auto_enabled,
)


class _MemDb:
    def __init__(self) -> None:
        self._path = ":memory:"
        self._read_only = False
        self._con = duckdb.connect(":memory:")

    def execute(self, sql: str, params=None):
        if params is not None:
            return self._con.execute(sql, params)
        return self._con.execute(sql)

    def query(self, sql: str):
        import json

        cur = self._con.execute(sql)
        cols = [d[0] for d in cur.description] if cur.description else []
        rows = cur.fetchall()
        return json.dumps([dict(zip(cols, row)) for row in rows])


def test_suggestions_auto_roundtrip() -> None:
    db = _MemDb()
    assert suggestions_auto_enabled(db, "c1") is None
    ok, err = set_suggestions_auto_enabled(db, "c1", False, tenant_id="t")
    assert ok and not err
    assert suggestions_auto_enabled(db, "c1") is False
    ok, err = set_suggestions_auto_enabled(db, "c1", True)
    assert ok
    assert suggestions_auto_enabled(db, "c1") is True
    # key suffix stored under chat_*_suggestions_auto
    raw = db.query(
        "SELECT key FROM agent_config WHERE key LIKE '%suggestions_auto%' LIMIT 1"
    )
    assert SUGGESTIONS_AUTO_KEY in raw
