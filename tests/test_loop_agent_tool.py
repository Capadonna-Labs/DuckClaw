"""Agent tools configure_loop_homeostasis / get_loop_homeostasis_status."""

from __future__ import annotations

import json

import pytest

from duckclaw.forge.skills.goals_tool_context import (
    set_goals_tool_chat_id,
    set_goals_tool_tenant_id,
    set_goals_tool_worker_id,
)
from duckclaw.forge.skills.loop_bridge import register_loop_skill


class _FakeDb:
    _path = "/tmp/test_vault.duckdb"

    def query(self, sql: str):
        return "[]"


def test_register_loop_skill_configure_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "duckclaw.graphs.on_the_fly_commands.apply_loop_schedule",
        lambda *_a, **_k: {"status": "disabled", "enabled": False},
    )
    tools: list = []
    register_loop_skill(tools, _FakeDb())
    names = {t.name for t in tools}
    assert "configure_loop_homeostasis" in names
    assert "get_loop_homeostasis_status" in names
    assert "request_homeostasis_validation" in names
    assert "configure_suggestions_auto" in names
    assert "pause_chat_autonomy" in names

    set_goals_tool_chat_id("chat-1")
    set_goals_tool_tenant_id("tenant-a")
    set_goals_tool_worker_id("analytics-worker")
    cfg = next(t for t in tools if t.name == "configure_loop_homeostasis")
    raw = cfg.invoke({"interval": "off"})
    data = json.loads(raw)
    assert data["status"] == "disabled"


def test_pause_chat_autonomy_disables_loop_and_suggestions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "duckclaw.graphs.on_the_fly_commands.apply_loop_schedule",
        lambda *_a, **_k: {"status": "disabled", "enabled": False},
    )
    calls: list[tuple] = []

    def _set_auto(db, chat_id, enabled, *, tenant_id="default"):
        calls.append((chat_id, enabled, tenant_id))
        return True, ""

    monkeypatch.setattr(
        "duckclaw.commands.suggestions_auto.set_suggestions_auto_enabled",
        _set_auto,
    )
    tools: list = []
    register_loop_skill(tools, _FakeDb())
    set_goals_tool_chat_id("chat-pause")
    set_goals_tool_tenant_id("t1")
    set_goals_tool_worker_id("quant_analyst")
    pause = next(t for t in tools if t.name == "pause_chat_autonomy")
    raw = pause.invoke({})
    data = json.loads(raw)
    assert data["status"] == "ok"
    assert data["suggestions_auto_enabled"] is False
    assert calls == [("chat-pause", False, "t1")]


def test_configure_suggestions_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []

    def _set_auto(db, chat_id, enabled, *, tenant_id="default"):
        calls.append((chat_id, enabled, tenant_id))
        return True, ""

    monkeypatch.setattr(
        "duckclaw.commands.suggestions_auto.set_suggestions_auto_enabled",
        _set_auto,
    )
    tools: list = []
    register_loop_skill(tools, _FakeDb())
    set_goals_tool_chat_id("chat-auto")
    set_goals_tool_tenant_id("default")
    set_goals_tool_worker_id("w1")
    cfg = next(t for t in tools if t.name == "configure_suggestions_auto")
    raw = cfg.invoke({"enabled": False})
    data = json.loads(raw)
    assert data["status"] == "ok"
    assert data["suggestions_auto_enabled"] is False
    assert calls == [("chat-auto", False, "default")]


def test_register_loop_skill_enable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "duckclaw.graphs.on_the_fly_commands.apply_loop_schedule",
        lambda *_a, **_k: {
            "status": "ok",
            "enabled": True,
            "interval_seconds": 600,
            "interval_human": "10 min",
            "first_cycle_executed": True,
        },
    )
    tools: list = []
    register_loop_skill(tools, _FakeDb())
    set_goals_tool_chat_id("chat-2")
    set_goals_tool_tenant_id("default")
    set_goals_tool_worker_id("analytics-worker")
    cfg = next(t for t in tools if t.name == "configure_loop_homeostasis")
    raw = cfg.invoke({"interval": "10min"})
    data = json.loads(raw)
    assert data["status"] == "ok"
    assert data.get("enabled") is True
