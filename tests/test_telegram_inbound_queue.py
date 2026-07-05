from __future__ import annotations

import json


def test_telegram_inbound_queue_enabled_default_off(monkeypatch) -> None:
    from duckclaw.telegram_inbound_queue import telegram_inbound_queue_enabled

    monkeypatch.delenv("DUCKCLAW_TELEGRAM_INBOUND_QUEUE", raising=False)
    assert telegram_inbound_queue_enabled() is False


def test_telegram_inbound_queue_enabled_on(monkeypatch) -> None:
    from duckclaw.telegram_inbound_queue import telegram_inbound_queue_enabled

    monkeypatch.setenv("DUCKCLAW_TELEGRAM_INBOUND_QUEUE", "1")
    assert telegram_inbound_queue_enabled() is True


def test_enqueue_and_dequeue_telegram_update(monkeypatch) -> None:
    from duckclaw.telegram_inbound_queue import (
        TELEGRAM_INBOUND_QUEUE_KEY,
        dequeue_telegram_update,
        enqueue_telegram_update,
    )

    queue: list[str] = []

    class FakeRedis:
        def lpush(self, key: str, value: str) -> int:
            assert key == TELEGRAM_INBOUND_QUEUE_KEY
            queue.insert(0, value)
            return len(queue)

        def brpop(self, key: str, timeout: int = 0):
            if not queue:
                return None
            return key, queue.pop()

        def rpop(self, key: str):
            return queue.pop() if queue else None

        def llen(self, key: str) -> int:
            return len(queue)

    fake = FakeRedis()
    monkeypatch.setattr("duckclaw.telegram_inbound_queue._redis_client", lambda: fake)

    payload = {
        "worker_id": "default",
        "tenant_id": "tenant_a",
        "session_id": "12345",
        "reply_token": "bot:secret",
        "chat_id": 12345,
        "user_id": "99",
        "username": "alice",
        "chat_type": "private",
        "message": "hola",
        "update_id": 42,
    }
    job_id = enqueue_telegram_update(payload)
    assert job_id.startswith("tgin_")
    assert fake.llen(TELEGRAM_INBOUND_QUEUE_KEY) == 1

    raw = queue[0]
    parsed = json.loads(raw)
    assert parsed["worker_id"] == "default"
    assert parsed["tenant_id"] == "tenant_a"
    assert parsed["message"] == "hola"
    assert parsed["update_id"] == 42
    assert parsed["job_id"] == job_id
    assert isinstance(parsed.get("enqueued_at"), float)

    job = dequeue_telegram_update(block_timeout_sec=0)
    assert job is not None
    assert job["job_id"] == job_id
    assert job["chat_id"] == 12345
    assert job["message"] == "hola"
