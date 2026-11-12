from __future__ import annotations

import pytest


def test_indexer_guard_blocks_gateway(monkeypatch) -> None:
    from duckclaw.knowledge_indexer_guard import (
        KnowledgeIndexingInGatewayError,
        assert_indexer_process_for_mutation,
    )

    monkeypatch.setenv("DUCKCLAW_PROCESS_ROLE", "gateway")
    monkeypatch.delenv("DUCKCLAW_GATEWAY_EMBED_KNOWLEDGE_SYNC", raising=False)
    with pytest.raises(KnowledgeIndexingInGatewayError):
        assert_indexer_process_for_mutation(operation="folder_sync")


def test_indexer_guard_allows_indexer_process(monkeypatch) -> None:
    from duckclaw.knowledge_indexer_guard import assert_indexer_process_for_mutation

    monkeypatch.setenv("DUCKCLAW_PROCESS_ROLE", "knowledge-indexer")
    assert_indexer_process_for_mutation(operation="folder_sync")


def test_worker_survives_a_dropped_redis_connection(monkeypatch) -> None:
    """A Redis error in one cycle used to kill the worker task; the process stayed online and consumed nothing."""
    import asyncio
    import importlib.util
    from pathlib import Path

    import duckclaw.knowledge_sync_queue as q

    spec = importlib.util.spec_from_file_location("ki_main", Path(__file__).resolve().parents[1] / "services" / "knowledge-indexer" / "main.py")
    main = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(main)
    calls = []

    def cycle(**_kw):
        calls.append(1)
        if len(calls) == 1:
            raise ConnectionError("Connection closed by server.")
        raise asyncio.CancelledError  # second cycle reached: stop the loop

    async def no_sleep(_s):
        return None

    monkeypatch.setattr(q, "run_knowledge_indexer_cycle", cycle)
    monkeypatch.setattr(main.asyncio, "sleep", no_sleep)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main._indexer_worker())
    assert len(calls) == 2
