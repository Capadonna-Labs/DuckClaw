from __future__ import annotations

import pytest


def test_knowledge_embed_batch_size_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_KNOWLEDGE_EMBED_BATCH_SIZE", raising=False)
    from duckclaw.knowledge_indexer_config import knowledge_embed_batch_size

    assert knowledge_embed_batch_size() == 32


def test_knowledge_embed_batch_size_parses_and_clamps(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.knowledge_indexer_config import knowledge_embed_batch_size

    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_EMBED_BATCH_SIZE", "64")
    assert knowledge_embed_batch_size() == 64

    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_EMBED_BATCH_SIZE", "0")
    assert knowledge_embed_batch_size() == 1

    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_EMBED_BATCH_SIZE", "999")
    assert knowledge_embed_batch_size() == 256

    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_EMBED_BATCH_SIZE", "bad")
    assert knowledge_embed_batch_size() == 32


def test_knowledge_indexer_max_inflight_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_KNOWLEDGE_INDEXER_MAX_INFLIGHT", raising=False)
    from duckclaw.knowledge_indexer_config import knowledge_indexer_max_inflight

    assert knowledge_indexer_max_inflight() == 1


def test_knowledge_indexer_max_inflight_parses_and_clamps(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.knowledge_indexer_config import knowledge_indexer_max_inflight

    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_INDEXER_MAX_INFLIGHT", "3")
    assert knowledge_indexer_max_inflight() == 3

    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_INDEXER_MAX_INFLIGHT", "0")
    assert knowledge_indexer_max_inflight() == 1

    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_INDEXER_MAX_INFLIGHT", "99")
    assert knowledge_indexer_max_inflight() == 8


def test_knowledge_queue_depth_warn_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.knowledge_indexer_config import knowledge_queue_depth_warn_threshold

    monkeypatch.delenv("DUCKCLAW_KNOWLEDGE_QUEUE_DEPTH_WARN", raising=False)
    assert knowledge_queue_depth_warn_threshold() == 10

    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_QUEUE_DEPTH_WARN", "25")
    assert knowledge_queue_depth_warn_threshold() == 25

    monkeypatch.setenv("DUCKCLAW_KNOWLEDGE_QUEUE_DEPTH_WARN", "nope")
    assert knowledge_queue_depth_warn_threshold() == 10
