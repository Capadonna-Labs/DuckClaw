from __future__ import annotations


def test_embed_goals_ticker_defaults_false(monkeypatch) -> None:
    from duckclaw.process_role import embed_goals_ticker_in_gateway

    monkeypatch.delenv("DUCKCLAW_EMBED_GOALS_TICKER", raising=False)
    assert embed_goals_ticker_in_gateway() is False


def test_gateway_embedding_policy_remote_only_by_default(monkeypatch) -> None:
    from duckclaw.process_role import gateway_embedding_policy

    monkeypatch.delenv("DUCKCLAW_GATEWAY_EMBEDDING_POLICY", raising=False)
    assert gateway_embedding_policy() == "remote_only"


def test_process_role_from_pm2_name(monkeypatch) -> None:
    from duckclaw.process_role import is_knowledge_indexer_process, process_role

    monkeypatch.delenv("DUCKCLAW_PROCESS_ROLE", raising=False)
    monkeypatch.setenv("DUCKCLAW_PM2_PROCESS_NAME", "DuckClaw-Knowledge-Indexer")
    assert process_role() == "knowledge-indexer"
    assert is_knowledge_indexer_process() is True
