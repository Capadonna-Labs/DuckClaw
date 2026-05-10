"""Handler db-writer: SEMANTIC_MEMORY_UPSERT y CONVERSATION_COMPACTION."""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import duckdb
import pytest

_REPO = Path(__file__).resolve().parents[1]
_DW = _REPO / "services" / "db-writer"
if str(_DW) not in sys.path:
    sys.path.insert(0, str(_DW))

from models.quant_state_delta import QuantStateDelta  # noqa: E402
from quant_state_delta_handler import (  # noqa: E402
    _DREAMER_SEMANTIC_TELEGRAM_DDL,
    _apply_delta,
)


def _exec_bundle(con: duckdb.DuckDBPyConnection, ddl: str) -> None:
    for stmt in ddl.strip().split(";"):
        s = stmt.strip()
        if s:
            con.execute(s)


@pytest.fixture
def dreamer_db() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    _exec_bundle(con, _DREAMER_SEMANTIC_TELEGRAM_DDL)
    yield con
    con.close()


def test_semantic_memory_upsert_inserts(dreamer_db: duckdb.DuckDBPyConnection) -> None:
    d = QuantStateDelta(
        tenant_id="1726618406",
        delta_type="SEMANTIC_MEMORY_UPSERT",
        user_id="1726618406",
        target_db_path="/tmp/x.duckdb",
        mutation={
            "table": "main.semantic_memory",
            "topic": "t1",
            "insight": "insight text",
            "confidence_score": 0.82,
            "source": "dreamer_job",
        },
    )
    _apply_delta(dreamer_db, d)
    row = dreamer_db.execute("SELECT topic, content, confidence_score FROM main.semantic_memory").fetchone()
    assert row is not None
    assert row[0] == "t1"
    assert row[1] == "insight text"
    assert abs(float(row[2]) - 0.82) < 1e-9


def test_conversation_compaction_deletes_old(dreamer_db: duckdb.DuckDBPyConnection) -> None:
    old = datetime.now(timezone.utc) - timedelta(days=30)
    dreamer_db.execute(
        """
        INSERT INTO telegram_conversation (chat_id, role, content, received_at)
        VALUES (1726618406, 'user', 'viejo', ?)
        """,
        [old],
    )
    dreamer_db.execute(
        """
        INSERT INTO telegram_conversation (chat_id, role, content, received_at)
        VALUES (1726618406, 'user', 'reciente', CURRENT_TIMESTAMP)
        """
    )
    n_before = dreamer_db.execute("SELECT COUNT(*) FROM telegram_conversation").fetchone()[0]
    assert n_before == 2

    d = QuantStateDelta(
        tenant_id="1726618406",
        delta_type="CONVERSATION_COMPACTION",
        user_id="1726618406",
        target_db_path="/tmp/x.duckdb",
        mutation={
            "table": "telegram_conversation",
            "chat_id": 1726618406,
            "days": 7,
        },
    )
    _apply_delta(dreamer_db, d)
    n_after = dreamer_db.execute("SELECT COUNT(*) FROM telegram_conversation").fetchone()[0]
    assert n_after == 1
    left = dreamer_db.execute("SELECT content FROM telegram_conversation").fetchone()[0]
    assert left == "reciente"
