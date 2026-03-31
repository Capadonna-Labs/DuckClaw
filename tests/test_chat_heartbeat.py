"""Tests para /heartbeat (Redis + outbound fire-and-forget)."""

from __future__ import annotations

import sys
import time
import types

import pytest


def test_heartbeat_redis_key_format() -> None:
    from duckclaw.graphs.chat_heartbeat import heartbeat_chat_alias_key, heartbeat_redis_key

    assert heartbeat_redis_key("tenant_a", "123") == "duckclaw:heartbeat:tenant_a:123"
    assert heartbeat_redis_key("", "") == "duckclaw:heartbeat:default:unknown"
    assert heartbeat_chat_alias_key("123") == "duckclaw:heartbeat:chat:123"


def test_normalize_telegram_chat_id_for_outbound() -> None:
    from duckclaw.graphs.chat_heartbeat import normalize_telegram_chat_id_for_outbound

    assert normalize_telegram_chat_id_for_outbound("1726618406") == "1726618406"
    assert normalize_telegram_chat_id_for_outbound("@Juan (1726618406)") == "1726618406"
    assert normalize_telegram_chat_id_for_outbound("-1001234567890") == "-1001234567890"


def test_is_chat_heartbeat_enabled_matches_numeric_key_for_display_chat_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    store: dict[str, str] = {"duckclaw:heartbeat:chat:1726618406": "on"}

    class FakeClient:
        def get(self, key: str) -> str | None:
            return store.get(key)

        def setex(self, key: str, _ttl: int, value: str) -> None:
            store[key] = value

    class FakeRedis:
        @staticmethod
        def from_url(_url: str, **_kwargs: object) -> FakeClient:
            return FakeClient()

    fake_redis_mod = types.ModuleType("redis")
    fake_redis_mod.Redis = FakeRedis  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "redis", fake_redis_mod)

    from duckclaw.graphs.chat_heartbeat import is_chat_heartbeat_enabled

    assert is_chat_heartbeat_enabled("SIATA", "@Juan (1726618406)") is True


def test_format_delegation_heartbeat_message_includes_title_and_tasks() -> None:
    from duckclaw.graphs.chat_heartbeat import format_delegation_heartbeat_message

    msg = format_delegation_heartbeat_message(
        "Gráfico de contaminación semanal",
        [
            "Obtener datos de los últimos 7 días",
            "Procesar y visualizar",
        ],
        task_summary="Resumen corto",
    )
    assert "Gráfico de contaminación semanal" in msg
    assert "Pasos que voy siguiendo:" in msg
    assert "1. Obtener datos" in msg


def test_format_delegation_heartbeat_message_subagent_header_in_opener() -> None:
    from duckclaw.graphs.chat_heartbeat import format_delegation_heartbeat_message

    msg = format_delegation_heartbeat_message(
        "Saludo",
        ["Uno"],
        subagent_header="BI-Analyst 1",
    )
    assert msg.startswith("📖 BI-Analyst 1 — Acabo de recibir")
    assert "Saludo" in msg


def test_heartbeat_env_int_treats_empty_or_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.graphs.chat_heartbeat import _heartbeat_env_int

    monkeypatch.setenv("DUCKCLAW_HEARTBEAT_TEST_INT", "")
    assert _heartbeat_env_int("DUCKCLAW_HEARTBEAT_TEST_INT", 42) == 42
    monkeypatch.setenv("DUCKCLAW_HEARTBEAT_TEST_INT", "not-a-number")
    assert _heartbeat_env_int("DUCKCLAW_HEARTBEAT_TEST_INT", 7) == 7


def test_format_tool_heartbeat_prefix() -> None:
    from duckclaw.graphs.chat_heartbeat import format_tool_heartbeat, heartbeat_message_for_tool

    raw = heartbeat_message_for_tool("read_sql")
    assert format_tool_heartbeat(None, raw) == raw
    assert format_tool_heartbeat("", raw) == raw
    combined = format_tool_heartbeat("BI-Analyst 2", raw)
    assert combined.startswith("BI-Analyst 2 — ")
    assert raw in combined
    with_plan = format_tool_heartbeat("BI-Analyst 1", raw, plan_title="Scatter de ventas")
    assert with_plan.startswith("BI-Analyst 1 — ")
    assert "📋 Scatter de ventas" in with_plan
    assert raw in with_plan
    with_elapsed = format_tool_heartbeat("W", raw, elapsed_sec=12.345)
    assert "⏱️ 12.3s" in with_elapsed


def test_format_heartbeat_elapsed_minutes() -> None:
    from duckclaw.graphs.chat_heartbeat import format_heartbeat_elapsed

    assert format_heartbeat_elapsed(None) == ""
    assert "2.0s" in format_heartbeat_elapsed(2.0)
    assert format_heartbeat_elapsed(125.0) == "⏱️ 2m 5s"


def test_heartbeat_message_for_tool_mapping() -> None:
    from duckclaw.graphs.chat_heartbeat import heartbeat_message_for_tool

    s = heartbeat_message_for_tool("get_schema_info").lower()
    assert "get_schema_info" in s and "columnas" in s
    rs = heartbeat_message_for_tool("read_sql")
    assert "sql" in rs.lower()
    assert "siata" not in rs.lower()
    assert "sql" in heartbeat_message_for_tool("admin_sql").lower()
    assert "sandbox" in heartbeat_message_for_tool("run_sandbox").lower()
    assert "inspect_schema" in heartbeat_message_for_tool("inspect_schema").lower()
    r = heartbeat_message_for_tool("scrape_siata_radar_realtime").lower()
    assert "radar" in r and "scrape_siata_radar_realtime" in r
    assert "custom_xyz" in heartbeat_message_for_tool("custom_xyz")
    assert "🔄" in heartbeat_message_for_tool("other_tool")


def test_set_and_read_heartbeat_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    store: dict[str, str] = {}

    class FakeClient:
        def setex(self, key: str, _ttl: int, value: str) -> None:
            store[key] = value

        def get(self, key: str) -> str | None:
            return store.get(key)

    class FakeRedis:
        @staticmethod
        def from_url(_url: str, **_kwargs: object) -> FakeClient:
            return FakeClient()

    fake_redis_mod = types.ModuleType("redis")
    fake_redis_mod.Redis = FakeRedis  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "redis", fake_redis_mod)

    from duckclaw.graphs.chat_heartbeat import (
        heartbeat_redis_key,
        is_chat_heartbeat_enabled,
        set_chat_heartbeat_enabled,
    )

    tid, cid = "default", "999"
    key = heartbeat_redis_key(tid, cid)
    ok, err = set_chat_heartbeat_enabled(tid, cid, True)
    assert ok and not err
    assert store.get(key) == "on"
    alias_k = f"duckclaw:heartbeat:chat:{cid}"
    assert store.get(alias_k) == "on"
    assert is_chat_heartbeat_enabled(tid, cid) is True
    ok2, err2 = set_chat_heartbeat_enabled(tid, cid, False)
    assert ok2 and not err2
    assert is_chat_heartbeat_enabled(tid, cid) is False


def test_is_chat_heartbeat_enabled_finds_gateway_tenant_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si solo existe la clave antigua SIATA:chat, el grafo con tenant 'default' debe verla."""
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("DUCKCLAW_GATEWAY_TENANT_ID", "SIATA")
    store: dict[str, str] = {"duckclaw:heartbeat:SIATA:999": "on"}

    class FakeClient:
        def get(self, key: str) -> str | None:
            return store.get(key)

        def setex(self, key: str, _ttl: int, value: str) -> None:
            store[key] = value

    class FakeRedis:
        @staticmethod
        def from_url(_url: str, **_kwargs: object) -> FakeClient:
            return FakeClient()

    fake_redis_mod = types.ModuleType("redis")
    fake_redis_mod.Redis = FakeRedis  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "redis", fake_redis_mod)

    from duckclaw.graphs.chat_heartbeat import is_chat_heartbeat_enabled

    assert is_chat_heartbeat_enabled("default", "999") is True


def test_heartbeat_outbound_prefers_duckclaw_heartbeat_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("N8N_OUTBOUND_WEBHOOK_URL", "https://example.test/wrong")
    monkeypatch.setenv("DUCKCLAW_HEARTBEAT_WEBHOOK_URL", "https://example.test/heartbeat-out")
    from duckclaw.graphs.chat_heartbeat import heartbeat_outbound_webhook_url

    assert heartbeat_outbound_webhook_url() == "https://example.test/heartbeat-out"


def test_schedule_chat_heartbeat_runs_post_in_background(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("N8N_OUTBOUND_WEBHOOK_URL", "https://example.test/out")
    posted: list[tuple[str, str, str]] = []

    def fake_post(cid: str, uid: str, text: str, **_: object) -> None:
        posted.append((cid, uid, text))

    monkeypatch.setattr(
        "duckclaw.graphs.chat_heartbeat.is_chat_heartbeat_enabled",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "duckclaw.graphs.chat_heartbeat._post_outbound_sync",
        fake_post,
    )
    from duckclaw.graphs.chat_heartbeat import schedule_chat_heartbeat_dm

    schedule_chat_heartbeat_dm("default", "42", "42", "ping")
    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline and not posted:
        time.sleep(0.01)
    assert posted == [("42", "42", "ping")]


def test_handle_command_heartbeat_on_requires_redis(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("DUCKCLAW_REDIS_URL", raising=False)
    from duckclaw.graphs.on_the_fly_commands import handle_command

    class _Db:
        def execute(self, *_a: object, **_k: object) -> None:
            pass

        def query(self, *_a: object, **_k: object) -> list:
            return []

    out = handle_command(_Db(), "1", "/heartbeat on", tenant_id="default")
    assert out is not None
    assert "redis" in (out or "").lower()
