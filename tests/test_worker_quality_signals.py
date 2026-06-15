from __future__ import annotations

import duckdb
import json


class _DuckDbAdapter:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def execute(self, sql: str, params=None):
        if params is not None:
            return self._con.execute(sql, params)
        return self._con.execute(sql)

    def query(self, sql: str) -> str:
        cur = self._con.execute(sql)
        cols = [d[0] for d in (cur.description or [])]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        return json.dumps(rows)


def test_worker_quality_signals_roundtrip_db_first() -> None:
    from duckclaw.worker_quality_signals import (
        QUALITY_SIGNALS_DOMAIN,
        list_worker_quality_signals,
        upsert_worker_quality_signal,
    )

    con = duckdb.connect(":memory:")
    try:
        db = _DuckDbAdapter(con)
        upsert_worker_quality_signal(
            db,
            tenant_id="tenant_a",
            worker_id="analytics-worker",
            key="latency_ms",
            target=250.0,
            threshold=25.0,
            comparison="ceiling",
            label="Latencia",
            updated_by="admin@test.local",
        )

        rows = list_worker_quality_signals(db, tenant_id="tenant_a", worker_id="analytics-worker")
    finally:
        con.close()

    assert QUALITY_SIGNALS_DOMAIN == "worker.quality_signals"
    assert len(rows) == 1
    assert rows[0].key == "latency_ms"
    assert rows[0].target == 250.0
    assert rows[0].threshold == 25.0
    assert rows[0].comparison == "ceiling"
    assert rows[0].label == "Latencia"


def test_worker_quality_signals_feed_goals_registry() -> None:
    from duckclaw.commands.chat_state import set_chat_state
    from duckclaw.commands.goals import _get_goals_registry_for_chat
    from duckclaw.worker_quality_signals import upsert_worker_quality_signal

    con = duckdb.connect(":memory:")
    try:
        db = _DuckDbAdapter(con)
        set_chat_state(db, "chat-1", "worker_id", "analytics-worker")
        upsert_worker_quality_signal(
            db,
            tenant_id="tenant_a",
            worker_id="analytics-worker",
            key="error_rate_pct",
            target=2.0,
            threshold=0.5,
            comparison="ceiling",
        )

        registry = _get_goals_registry_for_chat(db, "chat-1", tenant_id="tenant_a")
    finally:
        con.close()

    assert registry is not None
    belief = registry.get_belief("error_rate_pct")
    assert belief is not None
    assert belief.target == 2.0
    assert belief.threshold == 0.5
    assert belief.comparison == "ceiling"
