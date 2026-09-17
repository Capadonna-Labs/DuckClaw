"""Heartbeat /loop --delta must not leave pending_tick=1 after a successful tick.

Regression: setting pending after an awaited POST (while gateway already
touched last_activity) forced silence >= 2× interval while the chat footer
promised the next cycle in 1× interval (~25m → ~50m gaps).
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest

import services.heartbeat.main as heartbeat


class _ScanDb:
    def __init__(self, rows: dict[str, str]) -> None:
        self._rows = rows

    def query(self, sql: str) -> str:
        if "key LIKE 'chat_%_loop_delta_seconds'" in sql:
            out = [
                {"key": k, "value": v}
                for k, v in self._rows.items()
                if k.endswith("_loop_delta_seconds") or k.endswith("_meditate_delta_seconds")
            ]
            return json.dumps(out)
        if "SELECT value FROM agent_config" in sql:
            key = sql.split("key = '", 1)[1].split("'", 1)[0]
            val = self._rows.get(key, "")
            return json.dumps([{"value": val}]) if val else json.dumps([])
        return json.dumps([])

    def execute(self, sql: str) -> list[Any]:
        return []

    def __enter__(self) -> "_ScanDb":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


def _chat_key(chat_id: str, key: str) -> str:
    return f"chat_{chat_id}_{key}"


def test_idle_tick_success_clears_pending_and_reanchors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 1_700_000_000.0
    delta = 1500
    chat_id = "quant11"
    rows = {
        _chat_key(chat_id, "loop_delta_seconds"): str(delta),
        _chat_key(chat_id, "loop_delta_idle"): "1",
        _chat_key(chat_id, "loop_last_activity_epoch"): str(now - float(delta) - 5.0),
        _chat_key(chat_id, "loop_pending_tick"): "0",
        _chat_key(chat_id, "loop_worker_id"): "quant-worker",
        _chat_key(chat_id, "loop_tenant_id"): "default",
    }
    writes: list[tuple[str, str]] = []

    monkeypatch.setattr(
        heartbeat,
        "duckclaw_open_for_read_scan",
        lambda _path: _ScanDb(rows),
    )

    async def _capture_write(**kwargs: Any) -> None:
        writes.append((str(kwargs["key"]), str(kwargs["value"])))

    monkeypatch.setattr(heartbeat, "_enqueue_chat_state_write", _capture_write)

    async def _ok_tick(**_kwargs: Any) -> dict[str, Any]:
        return {"ok": True, "status_code": 200}

    monkeypatch.setattr(
        "duckclaw.commands.loop.post_loop_self_tick_async",
        _ok_tick,
    )
    monkeypatch.setattr(
        "duckclaw.graphs.activity.get_activity",
        lambda *_a, **_k: {"status": "IDLE"},
    )
    monkeypatch.setattr(heartbeat.time, "time", lambda: now + 10.0)

    asyncio.run(
        heartbeat._run_loop_proactive_tick_one_db("/tmp/fake.duckdb", now=now, headers={})
    )

    assert ("loop_pending_tick", "1") in writes  # in-flight guard before POST
    assert ("loop_pending_tick", "0") in writes  # cleared after success
    assert any(k == "loop_last_activity_epoch" for k, _ in writes)
    pending_writes = [v for k, v in writes if k == "loop_pending_tick"]
    assert pending_writes[-1] == "0"


def test_busy_due_tick_sets_catchup_and_skips_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 1_700_000_000.0
    delta = 1500
    chat_id = "quant11"
    rows = {
        _chat_key(chat_id, "loop_delta_seconds"): str(delta),
        _chat_key(chat_id, "loop_delta_idle"): "1",
        _chat_key(chat_id, "loop_last_activity_epoch"): str(now - float(delta) - 5.0),
        _chat_key(chat_id, "loop_pending_tick"): "0",
        _chat_key(chat_id, "loop_worker_id"): "quant-worker",
        _chat_key(chat_id, "loop_tenant_id"): "default",
    }
    writes: list[tuple[str, str]] = []
    posts: list[str] = []

    monkeypatch.setattr(
        heartbeat,
        "duckclaw_open_for_read_scan",
        lambda _path: _ScanDb(rows),
    )

    async def _capture_write(**kwargs: Any) -> None:
        writes.append((str(kwargs["key"]), str(kwargs["value"])))

    monkeypatch.setattr(heartbeat, "_enqueue_chat_state_write", _capture_write)

    async def _ok_tick(**_kwargs: Any) -> dict[str, Any]:
        posts.append("posted")
        return {"ok": True, "status_code": 200}

    monkeypatch.setattr(
        "duckclaw.commands.loop.post_loop_self_tick_async",
        _ok_tick,
    )
    monkeypatch.setattr(
        "duckclaw.graphs.activity.get_activity",
        lambda *_a, **_k: {"status": "BUSY"},
    )

    asyncio.run(
        heartbeat._run_loop_proactive_tick_one_db("/tmp/fake.duckdb", now=now, headers={})
    )

    assert ("loop_catchup_due", "1") in writes
    assert posts == []


def test_catchup_due_fires_even_when_silence_short(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 1_700_000_000.0
    delta = 1500
    chat_id = "quant11"
    rows = {
        _chat_key(chat_id, "loop_delta_seconds"): str(delta),
        _chat_key(chat_id, "loop_delta_idle"): "1",
        # Silence only 10s — normally not due, but catchup bypasses silence gate.
        _chat_key(chat_id, "loop_last_activity_epoch"): str(now - 10.0),
        _chat_key(chat_id, "loop_catchup_due"): "1",
        _chat_key(chat_id, "loop_pending_tick"): "0",
        _chat_key(chat_id, "loop_worker_id"): "quant-worker",
        _chat_key(chat_id, "loop_tenant_id"): "default",
    }
    writes: list[tuple[str, str]] = []

    monkeypatch.setattr(
        heartbeat,
        "duckclaw_open_for_read_scan",
        lambda _path: _ScanDb(rows),
    )

    async def _capture_write(**kwargs: Any) -> None:
        writes.append((str(kwargs["key"]), str(kwargs["value"])))

    monkeypatch.setattr(heartbeat, "_enqueue_chat_state_write", _capture_write)

    async def _ok_tick(**_kwargs: Any) -> dict[str, Any]:
        return {"ok": True, "status_code": 200}

    monkeypatch.setattr(
        "duckclaw.commands.loop.post_loop_self_tick_async",
        _ok_tick,
    )
    monkeypatch.setattr(
        "duckclaw.graphs.activity.get_activity",
        lambda *_a, **_k: {"status": "IDLE"},
    )
    monkeypatch.setattr(heartbeat.time, "time", lambda: now + 1.0)

    asyncio.run(
        heartbeat._run_loop_proactive_tick_one_db("/tmp/fake.duckdb", now=now, headers={})
    )

    assert ("loop_catchup_due", "0") in writes
    assert ("loop_pending_tick", "0") in writes

    now = 1_700_000_000.0
    delta = 1500
    chat_id = "quant11"
    rows = {
        _chat_key(chat_id, "loop_delta_seconds"): str(delta),
        _chat_key(chat_id, "loop_delta_idle"): "1",
        _chat_key(chat_id, "loop_last_activity_epoch"): str(now - float(delta) - 5.0),
        _chat_key(chat_id, "loop_pending_tick"): "0",
        _chat_key(chat_id, "loop_worker_id"): "quant-worker",
        _chat_key(chat_id, "loop_tenant_id"): "default",
    }
    writes: list[tuple[str, str]] = []

    monkeypatch.setattr(
        heartbeat,
        "duckclaw_open_for_read_scan",
        lambda _path: _ScanDb(rows),
    )

    async def _capture_write(**kwargs: Any) -> None:
        writes.append((str(kwargs["key"]), str(kwargs["value"])))

    monkeypatch.setattr(heartbeat, "_enqueue_chat_state_write", _capture_write)

    async def _fail_tick(**_kwargs: Any) -> dict[str, Any]:
        return {"ok": False, "status_code": 500, "body": "boom"}

    monkeypatch.setattr(
        "duckclaw.commands.loop.post_loop_self_tick_async",
        _fail_tick,
    )
    monkeypatch.setattr(
        "duckclaw.graphs.activity.get_activity",
        lambda *_a, **_k: {"status": "IDLE"},
    )

    asyncio.run(
        heartbeat._run_loop_proactive_tick_one_db("/tmp/fake.duckdb", now=now, headers={})
    )

    assert ("loop_pending_tick", "1") in writes
    assert ("loop_pending_tick", "0") in writes
    assert not any(k == "loop_last_activity_epoch" for k, _ in writes)


def test_pending_gate_skips_until_two_intervals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """While pending=1 (in-flight / stale), require silence >= 2× delta before re-fire."""
    now = 1_700_000_000.0
    delta = 1500
    chat_id = "quant11"
    rows = {
        _chat_key(chat_id, "loop_delta_seconds"): str(delta),
        _chat_key(chat_id, "loop_delta_idle"): "1",
        # silence == 1.5× delta → enough for normal fire, not for pending gate
        _chat_key(chat_id, "loop_last_activity_epoch"): str(now - float(delta) * 1.5),
        _chat_key(chat_id, "loop_pending_tick"): "1",
        _chat_key(chat_id, "loop_worker_id"): "quant-worker",
        _chat_key(chat_id, "loop_tenant_id"): "default",
    }
    posts: list[dict[str, Any]] = []

    monkeypatch.setattr(
        heartbeat,
        "duckclaw_open_for_read_scan",
        lambda _path: _ScanDb(rows),
    )

    async def _noop_write(**_kwargs: Any) -> None:
        return None

    monkeypatch.setattr(heartbeat, "_enqueue_chat_state_write", _noop_write)

    async def _capture_tick(**kwargs: Any) -> dict[str, Any]:
        posts.append(kwargs)
        return {"ok": True}

    monkeypatch.setattr(
        "duckclaw.commands.loop.post_loop_self_tick_async",
        _capture_tick,
    )

    asyncio.run(
        heartbeat._run_loop_proactive_tick_one_db("/tmp/fake.duckdb", now=now, headers={})
    )
    assert posts == []
