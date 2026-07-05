from __future__ import annotations

import json


def test_knowledge_sync_job_roundtrip() -> None:
    from duckclaw.knowledge_sync_queue import KnowledgeSyncJob

    job = KnowledgeSyncJob(
        job_id="ksync_test123",
        kind="folder_sync",
        source_id="ksrc_abc",
        tenant_id="tenant_a",
        actor_email="admin@test.com",
        force=True,
        compute_embeddings=False,
        enqueued_at=1234567890.0,
    )
    restored = KnowledgeSyncJob.from_json(job.to_json())
    assert restored.job_id == job.job_id
    assert restored.kind == "folder_sync"
    assert restored.force is True
    assert restored.compute_embeddings is False


def test_update_job_progress_merges_fields(monkeypatch) -> None:
    from duckclaw.knowledge_sync_queue import get_job_status, set_job_status, update_job_progress

    store: dict[str, str] = {}

    class FakeRedis:
        def set(self, key: str, value: str, ex: int | None = None) -> bool:
            store[key] = value
            return True

        def get(self, key: str):
            return store.get(key)

    monkeypatch.setattr("duckclaw.knowledge_sync_queue._redis_client", lambda: FakeRedis())

    job_id = "ksync_prog1"
    set_job_status(job_id, status="queued")
    update_job_progress(job_id, files_total=10, files_done=0, phase="indexing")
    update_job_progress(job_id, files_done=3, chunks_done=12, current_file="notes.md")

    status = get_job_status(job_id)
    assert status is not None
    assert status["status"] == "running"
    progress = status["progress"]
    assert progress["files_total"] == 10
    assert progress["files_done"] == 3
    assert progress["chunks_done"] == 12
    assert progress["current_file"] == "notes.md"


def test_enqueue_and_dequeue_job(monkeypatch) -> None:
    from duckclaw.knowledge_sync_queue import (
        KNOWLEDGE_SYNC_QUEUE_KEY,
        dequeue_knowledge_sync_job,
        enqueue_knowledge_sync_job,
        get_job_status,
    )

    store: dict[str, str] = {}
    queue: list[str] = []

    class FakeRedis:
        def lpush(self, key: str, value: str) -> int:
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

        def set(self, key: str, value: str, ex: int | None = None) -> bool:
            store[key] = value
            return True

        def get(self, key: str):
            return store.get(key)

    fake = FakeRedis()
    monkeypatch.setattr("duckclaw.knowledge_sync_queue._redis_client", lambda: fake)

    job_id = enqueue_knowledge_sync_job(
        kind="folder_ingest",
        source_id="ksrc_x",
        tenant_id="tenant_a",
        actor_email="admin@test.com",
    )
    assert job_id.startswith("ksync_")
    assert fake.llen(KNOWLEDGE_SYNC_QUEUE_KEY) == 1
    status = get_job_status(job_id)
    assert status is not None
    assert status["status"] == "queued"

    job = dequeue_knowledge_sync_job(block_timeout_sec=0)
    assert job is not None
    assert job.source_id == "ksrc_x"
    assert job.kind == "folder_ingest"
