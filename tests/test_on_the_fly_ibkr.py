"""Tests para el fly command /ibkr."""

from __future__ import annotations

from pathlib import Path

import pytest

from duckclaw import DuckClaw
from duckclaw.graphs.on_the_fly_commands import (
    execute_ibkr_toggle,
    get_chat_state,
    handle_command,
    set_chat_state,
)
from duckclaw.workers.factory import filter_tools_for_ibkr


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "finanz_test_ibkr_fly.duckdb")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    return DuckClaw(path)


def test_ibkr_on_requires_mode(db) -> None:
    chat_id = "test_ibkr_mode"
    reply = execute_ibkr_toggle(db, chat_id, "on")
    assert "mode" in reply.lower()
    assert get_chat_state(db, chat_id, "ibkr_enabled") != "true"


def test_ibkr_on_paper_persists(db) -> None:
    chat_id = "test_ibkr_paper"
    reply = execute_ibkr_toggle(db, chat_id, "on --mode paper")
    assert "activado" in reply.lower()
    assert get_chat_state(db, chat_id, "ibkr_enabled") == "true"
    assert get_chat_state(db, chat_id, "ibkr_portfolio_mode") == "paper"


def test_ibkr_on_live_persists(db) -> None:
    chat_id = "test_ibkr_live"
    reply = execute_ibkr_toggle(db, chat_id, "on --mode live")
    assert "live" in reply.lower()
    assert get_chat_state(db, chat_id, "ibkr_portfolio_mode") == "live"


def test_ibkr_off(db) -> None:
    chat_id = "test_ibkr_off"
    set_chat_state(db, chat_id, "ibkr_enabled", "true")
    set_chat_state(db, chat_id, "ibkr_portfolio_mode", "paper")

    reply = execute_ibkr_toggle(db, chat_id, "off")
    assert "desactivado" in reply.lower()
    assert get_chat_state(db, chat_id, "ibkr_enabled") == "false"


def test_handle_command_processes_ibkr(db) -> None:
    chat_id = "test_ibkr_handle"
    reply = handle_command(db, chat_id, "/ibkr on --mode paper")
    assert reply is not None
    assert get_chat_state(db, chat_id, "ibkr_enabled") == "true"


def test_filter_tools_for_ibkr() -> None:
    class DummyTool:
        def __init__(self, name: str) -> None:
            self.name = name

    tools = [DummyTool("read_sql"), DummyTool("get_ibkr_portfolio")]
    off = filter_tools_for_ibkr(tools, enabled=False)
    assert [t.name for t in off] == ["read_sql"]
    on = filter_tools_for_ibkr(tools, enabled=True)
    assert [t.name for t in on] == ["read_sql", "get_ibkr_portfolio"]
