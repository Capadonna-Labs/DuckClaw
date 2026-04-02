"""Modelo de estado de escritura y claves Redis alineadas con db-writer."""

from duckclaw.db_write_queue import (
    TASK_STATUS_TTL_SEC,
    DbWriteTaskStatus,
    task_status_redis_key,
)


def test_task_status_key_format() -> None:
    assert task_status_redis_key("abc") == "task_status:abc"


def test_task_status_ttl_positive() -> None:
    assert TASK_STATUS_TTL_SEC >= 30


def test_db_write_task_status_json_roundtrip() -> None:
    p = DbWriteTaskStatus(status="success")
    assert DbWriteTaskStatus.model_validate_json(p.model_dump_json()).status == "success"
    f = DbWriteTaskStatus(status="failed", detail="boom")
    r = DbWriteTaskStatus.model_validate_json(f.model_dump_json())
    assert r.status == "failed"
    assert r.detail == "boom"
