from __future__ import annotations

from typing import Any

import pytest

from duckclaw.db_write_fire_and_forget import (
    enqueue_write_and_resolve,
    resolve_write_enqueue_result,
    write_poll_timeout_sec,
)
from duckclaw.db_write_queue import DbWriteTaskStatus


def test_write_poll_timeout_sec_defaults_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_WRITE_POLL_SEC", raising=False)
    assert write_poll_timeout_sec() == 0.0


def test_resolve_write_enqueue_result_fire_and_forget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_WRITE_POLL_SEC", raising=False)
    ok, msg = resolve_write_enqueue_result("tid-1", None)
    assert ok is True
    assert msg == "Write encolado (task_id=tid-1)"


def test_resolve_write_enqueue_result_timeout_when_poll_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DUCKCLAW_WRITE_POLL_SEC", "5")
    ok, msg = resolve_write_enqueue_result("tid-2", None)
    assert ok is False
    assert msg == "timeout esperando db-writer"


def test_enqueue_write_and_resolve_skips_poll_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DUCKCLAW_WRITE_POLL_SEC", raising=False)
    redis_polled: list[str] = []

    def fake_enqueue(command: Any, *, db_path: str, user_id: str) -> str:
        return "tid-abc"

    monkeypatch.setattr(
        "duckclaw.db_write_fire_and_forget.enqueue_write_command",
        fake_enqueue,
    )
    monkeypatch.setattr(
        "duckclaw.db_write_queue.poll_task_status_sync",
        lambda task_id, **_kwargs: redis_polled.append(task_id),
    )

    ok, msg = enqueue_write_and_resolve(object(), db_path="/tmp/x.duckdb", user_id="u1")
    assert ok is True
    assert msg == "Write encolado (task_id=tid-abc)"
    assert redis_polled == []
