from __future__ import annotations

from unittest.mock import MagicMock, patch

from duckclaw.db_write_queue import DbWriteTaskStatus


def test_get_write_task_status_pending_when_missing() -> None:
    from duckclaw.gateway_enqueue import get_write_task_status

    fake = MagicMock()
    fake.get.return_value = None
    with patch("redis.from_url", return_value=fake):
        assert get_write_task_status("task_missing") is None


def test_get_write_task_status_parses_success() -> None:
    from duckclaw.gateway_enqueue import get_write_task_status

    payload = DbWriteTaskStatus(status="success").model_dump_json()
    fake = MagicMock()
    fake.get.return_value = payload
    with patch("redis.from_url", return_value=fake):
        row = get_write_task_status("task_ok")
    assert row is not None
    assert row["status"] == "success"
    assert row["task_id"] == "task_ok"
