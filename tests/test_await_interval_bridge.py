"""Tests for await_interval always-on tool."""

from __future__ import annotations

import json

import pytest

from duckclaw.forge.skills.await_interval_bridge import (
    DEFAULT_MAX_SECONDS,
    await_interval_impl,
    clamp_await_seconds,
    parse_await_duration,
    register_await_interval_skill,
)


def test_parse_await_duration_number_and_strings() -> None:
    assert parse_await_duration(5)[0] == 5.0
    assert parse_await_duration("5s")[0] == 5.0
    assert parse_await_duration("500ms")[0] == 0.5
    assert parse_await_duration("2m")[0] == 120.0
    assert parse_await_duration("1,5s")[0] == 1.5
    assert parse_await_duration("")[1] == "seconds_required"
    assert parse_await_duration("nope")[1] == "seconds_unparseable"


def test_clamp_await_seconds() -> None:
    assert clamp_await_seconds(0.01)[0] == pytest.approx(0.1)
    assert clamp_await_seconds(500) == (DEFAULT_MAX_SECONDS, True)
    assert clamp_await_seconds(3.0) == (3.0, False)


def test_await_interval_impl_sleeps_and_caps() -> None:
    slept: list[float] = []

    def _fake_sleep(secs: float) -> None:
        slept.append(secs)

    out = json.loads(await_interval_impl(2, reason="poll", sleeper=_fake_sleep))
    assert out["status"] == "ok"
    assert out["effective_seconds"] == 2.0
    assert out["capped"] is False
    assert out["reason"] == "poll"
    assert slept == [2.0]

    slept.clear()
    out = json.loads(await_interval_impl(999, sleeper=_fake_sleep))
    assert out["status"] == "ok"
    assert out["capped"] is True
    assert out["effective_seconds"] == DEFAULT_MAX_SECONDS
    assert slept == [DEFAULT_MAX_SECONDS]
    assert "Capado" in (out.get("note") or "")


def test_await_interval_impl_rejects_non_positive() -> None:
    out = json.loads(await_interval_impl(0, sleeper=lambda _s: None))
    assert out["status"] == "error"
    assert out["error"] == "seconds_must_be_positive"


def test_register_await_interval_skill_appends_tool() -> None:
    tools: list = []
    register_await_interval_skill(tools, db=None)
    assert len(tools) == 1
    assert tools[0].name == "await_interval"
    payload = json.loads(tools[0].invoke({"seconds": 0.2, "reason": "unit"}))
    assert payload["status"] == "ok"
    assert payload["effective_seconds"] == 0.2


def test_await_interval_in_core_pack_catalog() -> None:
    from duckclaw.workers.tool_pack_catalog import (
        clear_runtime_tool_pack_catalog_cache,
        load_default_runtime_tool_pack_catalog,
    )

    clear_runtime_tool_pack_catalog_cache()
    catalog = load_default_runtime_tool_pack_catalog()
    assert catalog.packs_for_tool("await_interval") == frozenset({"core"})
