"""Agent tools configure_crons_schedule / get_crons_schedule_status."""

from __future__ import annotations

import json

import pytest

from duckclaw.forge.skills.goals_tool_context import (
    set_goals_tool_chat_id,
    set_goals_tool_tenant_id,
)
from duckclaw.forge.skills.crons_bridge import register_crons_skill


class _FakeDb:
    _path = "/tmp/test_vault.duckdb"

    def query(self, sql: str):
        return "[]"


def test_register_crons_skill_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "duckclaw.graphs.on_the_fly_commands.execute_crons_schedule",
        lambda *_a, **_k: "Tus crons (programación)\n\n(sin schedules)",
    )
    tools: list = []
    register_crons_skill(tools, _FakeDb())
    names = {t.name for t in tools}
    assert "configure_crons_schedule" in names
    assert "get_crons_schedule_status" in names

    set_goals_tool_chat_id("chat-cron-1")
    set_goals_tool_tenant_id("tenant-a")
    status = next(t for t in tools if t.name == "get_crons_schedule_status")
    raw = status.invoke({})
    data = json.loads(raw)
    assert data["status"] == "ok"
    assert "message" in data


def test_configure_crons_schedule_wall_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def _fake_execute(db, chat_id, args, *, tenant_id=None, vault_user_id=None):
        captured["chat_id"] = chat_id
        captured["args"] = args
        captured["tenant_id"] = tenant_id
        return (
            "Programación por reloj guardada. every 08:30 lun (America/Bogota). "
            "Usa /crons para listar."
        )

    monkeypatch.setattr(
        "duckclaw.graphs.on_the_fly_commands.execute_crons_schedule",
        _fake_execute,
    )
    tools: list = []
    register_crons_skill(tools, _FakeDb())
    set_goals_tool_chat_id("chat-cron-2")
    set_goals_tool_tenant_id("default")
    cfg = next(t for t in tools if t.name == "configure_crons_schedule")
    raw = cfg.invoke({"command": "--timestamp every 08:30 lun"})
    data = json.loads(raw)
    assert data["status"] == "ok"
    assert captured["chat_id"] == "chat-cron-2"
    assert captured["args"] == "--timestamp every 08:30 lun"
    assert captured["tenant_id"] == "default"
    assert "reloj" in data["message"].lower() or "08:30" in data["message"]


def test_configure_crons_schedule_requires_chat_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "duckclaw.graphs.on_the_fly_commands.execute_crons_schedule",
        lambda *_a, **_k: "ok",
    )
    tools: list = []
    register_crons_skill(tools, _FakeDb())
    set_goals_tool_chat_id("")
    set_goals_tool_tenant_id("default")
    cfg = next(t for t in tools if t.name == "configure_crons_schedule")
    data = json.loads(cfg.invoke({"command": "--delta 20min"}))
    assert data["status"] == "error"
    assert "chat_id" in data["error"]
