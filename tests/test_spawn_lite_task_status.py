"""Tests for LITE_MODE / Spawn inline task_status and readiness."""

from __future__ import annotations

import asyncio

import pytest


def test_lite_mode_sets_spawn_profile(monkeypatch) -> None:
    from duckclaw.spawn_profile import apply_lite_mode_env, is_spawn_profile, spawn_inline_writes_enabled

    monkeypatch.delenv("DUCKCLAW_SPAWN_PROFILE", raising=False)
    monkeypatch.delenv("DUCKCLAW_SPAWN_USE_DB_WRITER", raising=False)
    monkeypatch.setenv("LITE_MODE", "1")

    apply_lite_mode_env()
    assert is_spawn_profile()
    assert spawn_inline_writes_enabled()


def test_inline_task_status_without_redis(monkeypatch) -> None:
    from duckclaw.db_write_queue import DbWriteTaskStatus, get_task_status_sync, poll_task_status_sync

    monkeypatch.setenv("LITE_MODE", "1")
    monkeypatch.setenv("DUCKCLAW_SPAWN_PROFILE", "1")
    monkeypatch.delenv("DUCKCLAW_SPAWN_USE_DB_WRITER", raising=False)

    from duckclaw.db_write_queue import _publish_inline_task_status

    _publish_inline_task_status("task-lite-1", DbWriteTaskStatus(status="success"))
    row = get_task_status_sync("task-lite-1")
    assert row is not None
    assert row.status == "success"
    polled = poll_task_status_sync("task-lite-1", timeout_sec=0.2)
    assert polled is not None
    assert polled.status == "success"


def test_gateway_enqueue_reads_inline_status(monkeypatch) -> None:
    from duckclaw.db_write_queue import DbWriteTaskStatus, _publish_inline_task_status
    from duckclaw.gateway_enqueue import get_write_task_status

    monkeypatch.setenv("LITE_MODE", "1")
    monkeypatch.setenv("DUCKCLAW_SPAWN_PROFILE", "1")
    monkeypatch.delenv("DUCKCLAW_SPAWN_USE_DB_WRITER", raising=False)

    _publish_inline_task_status("task-lite-2", DbWriteTaskStatus(status="failed", detail="boom"))
    out = get_write_task_status("task-lite-2")
    assert out == {"task_id": "task-lite-2", "status": "failed", "detail": "boom"}


def test_readiness_skips_redis_when_spawn_inline(monkeypatch, tmp_path) -> None:
    from duckclaw.infra.readiness import assert_gateway_startup_ready

    monkeypatch.setenv("LITE_MODE", "1")
    monkeypatch.setenv("DUCKCLAW_SPAWN_PROFILE", "1")
    monkeypatch.delenv("DUCKCLAW_SPAWN_USE_DB_WRITER", raising=False)

    db_path = tmp_path / "hub.duckdb"
    import duckdb

    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(str(db_path))
    try:
        run_pending_migrations(con)
    finally:
        con.close()

    async def _run() -> None:
        await assert_gateway_startup_ready(
            redis_url="redis://127.0.0.1:6399/0",
            gateway_db_path=str(db_path),
        )

    asyncio.run(_run())
