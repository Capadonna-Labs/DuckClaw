from __future__ import annotations

import importlib
import inspect
import json
from typing import Any

from duckclaw.graphs import on_the_fly_commands


CANONICAL_MODULE = "duckclaw.commands.history"
HISTORY_EXPORTS = (
    "_TASK_AUDIT_TABLE",
    "_ensure_task_audit_log",
    "_infer_user_id_for_audit_queue",
    "_is_simple_greeting",
    "_is_complex_task",
    "append_task_audit",
    "execute_history",
    "get_history_limit_for_chat",
)


def test_history_command_ownership_lives_outside_graphs() -> None:
    history = importlib.import_module(CANONICAL_MODULE)

    for name in HISTORY_EXPORTS:
        exported = getattr(on_the_fly_commands, name)
        canonical = getattr(history, name)
        if inspect.isfunction(canonical):
            assert exported.__module__ == CANONICAL_MODULE
        else:
            assert exported == canonical

    source = inspect.getsource(history)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source


def test_history_module_has_no_vertical_runtime_defaults_or_raw_queue_sql() -> None:
    history = importlib.import_module(CANONICAL_MODULE)
    source = inspect.getsource(history).lower()

    forbidden = {
        "quant",
        "trader",
        "finance",
        "platform-orchestrator",
        "ibkr",
        "pqrs",
        "pqrsd",
        "leila",
        "war room",
        "job hunter",
        "enqueue_duckdb_write_sync",
        "duckdb.connect",
    }
    leaked = sorted(marker for marker in forbidden if marker in source)

    assert leaked == []


def test_history_task_audit_writes_use_typed_db_writer_command() -> None:
    history = importlib.import_module(CANONICAL_MODULE)
    source = inspect.getsource(history)

    assert "AppendTaskAuditCommand" in source
    assert "enqueue_typed_command" in source


def test_history_round_trip_appends_and_lists_task_audit_row() -> None:
    import duckdb

    history = importlib.import_module(CANONICAL_MODULE)
    con = duckdb.connect(":memory:")
    db = _DuckDbTestAdapter(con)

    history.append_task_audit(
        db,
        "chat-1",
        "worker-a",
        "analiza latencia de plataforma",
        "SUCCESS",
        2500,
        plan_title="Analisis de latencia",
    )

    out = history.execute_history(db, "chat-1", "5")

    assert "[worker-a] Analisis de latencia" in out
    assert "avg 2.5s" in out


def test_on_the_fly_history_imports_remain_compatible() -> None:
    history = importlib.import_module(CANONICAL_MODULE)

    for name in HISTORY_EXPORTS:
        assert getattr(on_the_fly_commands, name) == getattr(history, name)


class _DuckDbTestAdapter:
    _read_only = False

    def __init__(self, con: Any) -> None:
        self._con = con

    def execute(self, sql: str, params: list[Any] | None = None) -> Any:
        return self._con.execute(sql, params or [])

    def query(self, sql: str) -> str:
        result = self._con.execute(sql)
        names = [d[0] for d in result.description]
        rows = [dict(zip(names, row)) for row in result.fetchall()]
        return json.dumps(rows, ensure_ascii=False, default=str)
