from __future__ import annotations

import importlib
import inspect
from typing import Any

from duckclaw.graphs import on_the_fly_commands


CANONICAL_MODULE = "duckclaw.commands.health"
HEALTH_FUNCTION_EXPORTS = (
    "execute_health",
    "execute_heartbeat",
)


def test_health_heartbeat_command_ownership_lives_outside_graphs() -> None:
    health = importlib.import_module(CANONICAL_MODULE)

    for name in HEALTH_FUNCTION_EXPORTS:
        exported = getattr(on_the_fly_commands, name)
        assert exported.__module__ == CANONICAL_MODULE
        assert exported is getattr(health, name)

    source = inspect.getsource(health)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source
    assert "duckclaw.graphs." not in source


def test_health_module_has_no_vertical_defaults_or_duckdb_writes() -> None:
    health = importlib.import_module(CANONICAL_MODULE)
    source = inspect.getsource(health).lower()

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
        "duckdb.connect",
        "read_only=false",
        "agent_config",
        "_set_global_config",
        "set_chat_state",
        "insert into",
        "update ",
        "delete from",
    }
    leaked = sorted(marker for marker in forbidden if marker in source)

    assert leaked == []


def test_execute_health_reads_duckdb_without_writes(monkeypatch: Any) -> None:
    health = importlib.import_module(CANONICAL_MODULE)
    db = _ReadOnlyDbProbe()

    monkeypatch.setenv("DUCKCLAW_LLM_BASE_URL", "http://127.0.0.1:9/v1")
    out = health.execute_health(db)

    assert "DuckDB: conectado" in out
    assert "Inferencia" in out
    assert db.queries == ["SELECT 1"]
    assert db.writes == []


def test_execute_heartbeat_uses_configured_adapter_without_graph_imports() -> None:
    health = importlib.import_module(CANONICAL_MODULE)
    adapter = _HeartbeatAdapterProbe(redis_configured=True, outbound_configured=False)

    health.configure_heartbeat_adapter(adapter)
    try:
        enabled = health.execute_heartbeat(None, "chat-1", "on", tenant_id="tenant-1")
        status = health.execute_heartbeat(None, "chat-1", "", tenant_id="tenant-1")
    finally:
        health.configure_heartbeat_adapter(None)

    assert "Heartbeat activado en DB" in enabled
    assert status == "Heartbeat: on\nUso: /heartbeat on | /heartbeat off"
    assert adapter.set_calls == [(None, "tenant-1", "chat-1", True)]


def test_on_the_fly_health_imports_remain_compatible() -> None:
    health = importlib.import_module(CANONICAL_MODULE)

    for name in HEALTH_FUNCTION_EXPORTS:
        assert getattr(on_the_fly_commands, name) is getattr(health, name)


class _ReadOnlyDbProbe:
    def __init__(self) -> None:
        self.queries: list[str] = []
        self.writes: list[str] = []

    def query(self, sql: str) -> str:
        self.queries.append(sql)
        return "ok"

    def execute(self, sql: str, params: list[Any] | None = None) -> None:
        del params
        self.writes.append(sql)


class _HeartbeatAdapterProbe:
    def __init__(self, *, redis_configured: bool, outbound_configured: bool) -> None:
        self._enabled = False
        self._redis_configured = redis_configured
        self._outbound_configured = outbound_configured
        self.set_calls: list[tuple[Any, str, str, bool]] = []

    def heartbeat_redis_configured(self) -> bool:
        return self._redis_configured

    def heartbeat_outbound_configured(self) -> bool:
        return self._outbound_configured

    def is_admin_ui_chat_session(self, chat_id: str) -> bool:
        del chat_id
        return False

    def is_chat_heartbeat_enabled(self, db: Any, tenant_id: str, chat_id: str) -> bool:
        del db, tenant_id, chat_id
        return self._enabled

    def set_chat_heartbeat_enabled(
        self, db: Any, tenant_id: str, chat_id: str, on: bool
    ) -> tuple[bool, str]:
        self.set_calls.append((db, tenant_id, chat_id, on))
        self._enabled = on
        return True, ""
