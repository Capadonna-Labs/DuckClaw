"""Tests unitarios de services/db-writer/main.py y db_writer_ops."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_WRITER_DIR = _REPO / "services" / "db-writer"


def _import_db_writer_main():
    """Import main del db-writer sin colisión con api-gateway/main.py."""
    writer_str = str(_WRITER_DIR)
    if writer_str not in sys.path:
        sys.path.insert(0, writer_str)
    import main as db_writer_main  # noqa: PLC0415

    return db_writer_main


def _import_db_writer_ops():
    writer_str = str(_WRITER_DIR)
    if writer_str not in sys.path:
        sys.path.insert(0, writer_str)
    import db_writer_ops  # noqa: PLC0415

    return db_writer_ops


class FakeAsyncRedis:
    """Redis async mínimo para task_status y métricas."""

    def __init__(self) -> None:
        self.setex_calls: list[tuple[str, int, str]] = []
        self._kv: dict[str, str] = {}

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.setex_calls.append((key, ttl, value))
        self._kv[key] = value

    async def get(self, key: str) -> str | None:
        return self._kv.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._kv[key] = value

    async def incrby(self, key: str, delta: int = 1) -> int:
        current = int(self._kv.get(key, "0"))
        current += delta
        self._kv[key] = str(current)
        return current


def test_invalid_json_publishes_failed_task_status() -> None:
    from duckclaw.db_write_queue import DbWriteTaskStatus, task_status_redis_key

    db_writer_main = _import_db_writer_main()
    redis_client = FakeAsyncRedis()

    asyncio.run(db_writer_main.execute_write(redis_client, "{not-json"))

    assert len(redis_client.setex_calls) == 1
    key, _ttl, raw = redis_client.setex_calls[0]
    assert key == task_status_redis_key("unknown")
    status = DbWriteTaskStatus.model_validate_json(raw)
    assert status.status == "failed"
    assert status.detail == "Formato JSON inválido"


def test_invalid_json_partial_task_id_in_status() -> None:
    from duckclaw.db_write_queue import DbWriteTaskStatus, task_status_redis_key

    db_writer_main = _import_db_writer_main()
    redis_client = FakeAsyncRedis()
    broken = '{"task_id": "partial-1", "command_type": broken'

    asyncio.run(db_writer_main.execute_write(redis_client, broken))

    assert redis_client.setex_calls
    key, _, raw = redis_client.setex_calls[0]
    assert key == task_status_redis_key("partial-1")
    status = DbWriteTaskStatus.model_validate_json(raw)
    assert status.status == "failed"


def test_raw_sql_handled_in_typed_sync_path(tmp_path: Path) -> None:
    db_writer_main = _import_db_writer_main()
    db_path = tmp_path / "raw_sql_typed.duckdb"

    outcome = db_writer_main._run_typed_command_sync(
        task_id="raw-t1",
        command_type="raw_sql",
        payload={
            "command_type": "raw_sql",
            "query": "CREATE TABLE main.probe_raw_sql (id INTEGER)",
            "params": [],
        },
        target_db_path=str(db_path),
    )

    assert outcome == "completed"
    import duckdb

    con = duckdb.connect(str(db_path), read_only=True)
    try:
        row = con.execute(
            "SELECT command_type, status FROM main.admin_write_ledger WHERE task_id = 'raw-t1'"
        ).fetchone()
        assert row is not None
        assert row[0] == "raw_sql"
        assert row[1] == "completed"
        tables = {
            r[0]
            for r in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
        }
        assert "probe_raw_sql" in tables
    finally:
        con.close()


def test_main_does_not_skip_raw_sql_in_typed_handler() -> None:
    source = (_WRITER_DIR / "main.py").read_text(encoding="utf-8")
    handler_block = source.split("async def _handle_typed_command", 1)[1].split(
        "async def _publish_task_status", 1
    )[0]
    assert 'command_type == "raw_sql"' not in handler_block
    assert 'if command_type == "raw_sql":' in source


def test_db_path_lock_registry_serializes_same_path() -> None:
    DbPathLockRegistry = _import_db_writer_ops().DbPathLockRegistry
    registry = DbPathLockRegistry()
    order: list[str] = []

    async def worker(tag: str) -> None:
        async with registry.acquire("/tmp/duckclaw-lock-test.duckdb"):
            order.append(f"{tag}-start")
            await asyncio.sleep(0.05)
            order.append(f"{tag}-end")

    async def run_workers() -> None:
        await asyncio.gather(worker("a"), worker("b"))

    asyncio.run(run_workers())

    assert order.index("a-start") < order.index("a-end")
    assert order.index("b-start") < order.index("b-end")
    assert (
        order == ["a-start", "a-end", "b-start", "b-end"]
        or order == ["b-start", "b-end", "a-start", "a-end"]
    )


def test_db_path_lock_allows_parallel_different_paths() -> None:
    DbPathLockRegistry = _import_db_writer_ops().DbPathLockRegistry
    registry = DbPathLockRegistry()
    overlap = asyncio.Event()
    started = 0

    async def worker(db_path: str) -> None:
        nonlocal started
        async with registry.acquire(db_path):
            started += 1
            if started == 1:
                overlap.set()
            await overlap.wait()

    async def run_workers() -> None:
        await asyncio.gather(worker("/tmp/a.duckdb"), worker("/tmp/b.duckdb"))

    asyncio.run(run_workers())
