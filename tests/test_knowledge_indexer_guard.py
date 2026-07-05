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
