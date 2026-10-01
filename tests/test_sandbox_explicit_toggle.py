"""Explicit sandbox ON keeps run_sandbox bound; the admin-UI default does not."""

from __future__ import annotations


def test_explicit_toggle_vs_admin_default(monkeypatch) -> None:
    from duckclaw import runtime_session_settings as rss
    from duckclaw.workers import factory_graph_nodes_prepare as prep

    stored: dict[str, str] = {}
    monkeypatch.setattr(
        rss, "resolve_session_runtime_setting", lambda _db, chat_id, _key, **_kw: stored.get(str(chat_id), "")
    )
    cid = "admin-conv-abc"
    # Nothing set: admin UI defaults ON, but that's not an explicit request.
    assert prep.sandbox_enabled_for_chat(None, cid, "t") is True
    assert prep.sandbox_explicitly_enabled_for_chat(None, cid, "t") is False
    stored[cid] = "true"  # /sandbox on or the admin switch
    assert prep.sandbox_explicitly_enabled_for_chat(None, cid, "t") is True
    stored[cid] = "false"
    assert prep.sandbox_enabled_for_chat(None, cid, "t") is False
    assert prep.sandbox_explicitly_enabled_for_chat(None, cid, "t") is False


def test_llm_usage_flags_replies_cut_by_max_tokens(caplog) -> None:
    """Reasoning models exhaust the output budget -> empty reply; must be visible in logs."""
    import logging

    from langchain_core.messages import AIMessage

    from duckclaw.workers.factory_graph_nodes_agent_shared import log_llm_usage

    cut = AIMessage(content="", response_metadata={"finish_reason": "length", "token_usage": {"completion_tokens": 2048}})
    with caplog.at_level(logging.INFO):
        log_llm_usage("quant_analyst", 0.0, response=cut)
        log_llm_usage("quant_analyst", 0.0, response=AIMessage(content="ok", response_metadata={"finish_reason": "stop"}))
    warned = [r for r in caplog.records if "truncated=max_tokens" in r.getMessage()]
    assert len(warned) == 1 and "completion_tokens=2048" in warned[0].getMessage()


def test_openrouter_default_output_budget_fits_reasoning_models(monkeypatch) -> None:
    monkeypatch.delenv("DUCKCLAW_OPENROUTER_MAX_OUTPUT_TOKENS", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    from duckclaw.integrations import llm_providers as lp

    llm = lp.build_openrouter_llm("deepseek/deepseek-v4-pro")
    assert llm.max_tokens == 8192
