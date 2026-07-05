"""Tests for PM2 stack health parser (admin overview metrics)."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from duckclaw.ops.pm2_stack_health import (
    PM2_JLIST_TIMEOUT_SEC,
    collect_pm2_stack_health,
    parse_pm2_jlist,
)


def test_parse_pm2_jlist_extracts_status_and_memory() -> None:
    payload = [
        {
            "name": "DuckClaw-Gateway",
            "pid": 100,
            "pm2_env": {"status": "online"},
            "monit": {"memory": 52_428_800},
        },
        {
            "name": "DuckClaw-DB-Writer",
            "pid": 200,
            "pm2_env": {
                "status": "online",
                "axm_monitor": {"Used Heap Size": "12.5 MiB"},
            },
            "monit": {"memory": 26_214_400},
        },
        {
            "name": "DuckClaw-Knowledge-Indexer",
            "pid": 0,
            "pm2_env": {"status": "stopped"},
            "monit": {"memory": 0},
        },
        {"name": "other-app", "pm2_env": {"status": "online"}, "monit": {"memory": 999}},
    ]

    rows = parse_pm2_jlist(payload)
    by_name = {row["name"]: row for row in rows}

    assert len(rows) == 4
    assert by_name["DuckClaw-Gateway"]["status"] == "online"
    assert by_name["DuckClaw-Gateway"]["rss_mb"] == 50.0
    assert by_name["DuckClaw-DB-Writer"]["rss_mb"] == 25.0
    assert by_name["DuckClaw-DB-Writer"]["heap_mb"] == 12.5
    assert by_name["DuckClaw-Knowledge-Indexer"]["status"] == "stopped"
    assert by_name["DuckClaw-Heartbeat"]["status"] == "missing"
    assert by_name["DuckClaw-Heartbeat"]["rss_mb"] is None


def test_parse_pm2_jlist_invalid_payload_returns_empty() -> None:
    assert parse_pm2_jlist({}) == []
    assert parse_pm2_jlist("not-json") == []


def test_collect_pm2_stack_health_uses_short_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = [
        {
            "name": "DuckClaw-DB-Writer",
            "pid": 42,
            "pm2_env": {"status": "online"},
            "monit": {"memory": 10_485_760},
        }
    ]
    seen: dict[str, int | None] = {}

    def fake_run_pm2(*args, timeout=None, **_kwargs):
        seen["args"] = list(args)
        seen["timeout"] = timeout
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")

    monkeypatch.setattr("duckclaw.ops.toolchain.run_pm2", fake_run_pm2)

    rows = collect_pm2_stack_health()
    writer = next(row for row in rows if row["name"] == "DuckClaw-DB-Writer")

    assert seen["args"] == ["jlist"]
    assert seen["timeout"] == PM2_JLIST_TIMEOUT_SEC
    assert writer["status"] == "online"
    assert writer["rss_mb"] == 10.0


def test_collect_pm2_stack_health_missing_pm2_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.ops.toolchain import ToolchainError

    def fake_run_pm2(*_args, **_kwargs):
        raise ToolchainError("pm2 not found")

    monkeypatch.setattr("duckclaw.ops.toolchain.run_pm2", fake_run_pm2)
    assert collect_pm2_stack_health() == []


def test_collect_gateway_health_metrics_includes_pm2_processes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.ops.gateway_health_metrics import collect_gateway_health_metrics

    monkeypatch.setattr(
        "duckclaw.ops.pm2_stack_health.collect_pm2_stack_health",
        lambda **_: [{"name": "DuckClaw-DB-Writer", "status": "online", "rss_mb": 32.0}],
    )

    metrics = collect_gateway_health_metrics()
    assert isinstance(metrics.get("pm2_processes"), list)
    assert metrics["pm2_processes"][0]["name"] == "DuckClaw-DB-Writer"
