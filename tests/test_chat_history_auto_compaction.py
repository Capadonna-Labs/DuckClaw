"""History token budget + pre-turn auto-summarize (replaces the silent 48-msg window)."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

_gw = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
if str(_gw) not in sys.path:
    sys.path.insert(0, str(_gw))


def _msgs(n: int, chars: int) -> list[dict[str, str]]:
    return [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"{i}:" + "x" * chars}
        for i in range(n)
    ]


def test_needs_compaction_at_97_percent_of_budget(monkeypatch) -> None:
    from core.chat_history import history_estimated_tokens, history_needs_compaction

    monkeypatch.setenv("DUCKCLAW_CHAT_HISTORY_TOKEN_BUDGET", "10000")
    below = [{"role": "user", "content": "x" * (4 * 9600)}]  # 9600 tokens < 9700
    above = [{"role": "user", "content": "x" * (4 * 9800)}]
    assert history_estimated_tokens(below) == 9600
    assert history_needs_compaction(below) is False
    assert history_needs_compaction(above) is True


def test_history_cap_no_longer_drops_at_48_messages(monkeypatch) -> None:
    """Regression: the fixed 48-message window silently dropped old turns, which
    kept the context meter pinned around 2% and nothing was ever summarized."""
    from core.chat_history import normalize_history_list

    monkeypatch.delenv("DUCKCLAW_CHAT_HISTORY_MAX_MSGS", raising=False)
    assert len(normalize_history_list(_msgs(120, 10))) == 120


def test_trim_fallback_keeps_newest_within_budget_starting_on_user(monkeypatch) -> None:
    from core.chat_history import history_estimated_tokens, trim_history_to_budget

    monkeypatch.setenv("DUCKCLAW_CHAT_HISTORY_TOKEN_BUDGET", "10000")
    history = _msgs(40, 4000)  # ~1000 tokens each
    kept = trim_history_to_budget(history)
    assert kept[-1] == history[-1]
    assert kept[0]["role"] == "user"
    assert history_estimated_tokens(kept) <= 5000


def _prepared(history: list[dict[str, Any]], vault: str = "/v/quant.duckdb"):
    from core.chat_invoke_prepare import PreparedChatInvoke

    return PreparedChatInvoke(
        payload=SimpleNamespace(),
        worker_id="quant_analyst",
        session_id="admin-conv-1",
        tenant_id="t1",
        message="hola",
        user_incoming="hola",
        chat_type="private",
        username="juan",
        user_id="juan",
        vault_user_id="juan",
        vault_db_path=vault,
        telegram_acl_for_guard=None,
        delivery_context=SimpleNamespace(),
        history_for_model=history,
        history_for_graph=history,
        is_system_prompt=False,
        skip_session_lock=True,
        shared_db_path=None,
        auth_policy="trusted_admin_console",
        is_owner=True,
        chat_ident="admin-conv-1",
        payload_vault=vault,
    )


def _patch_io(monkeypatch, *, fold_result, saved: dict) -> None:
    async def _fake_redis_save(_redis, tenant_id, session_id, items):
        saved["redis"] = items

    def _fake_save_summary(vault, chat_id, summary, tenant_id="default"):
        saved["summary"] = summary
        return True

    monkeypatch.setattr("core.chat_history.redis_save_chat_history", _fake_redis_save)
    monkeypatch.setattr(
        "duckclaw.commands.context_summarize.run_manual_context_fold",
        lambda *a, **k: fold_result,
    )
    monkeypatch.setattr(
        "duckclaw.commands.context_fold_store.save_context_fold_summary", _fake_save_summary
    )
    monkeypatch.setattr("duckclaw.gateway_db.GatewayDbEphemeralReadonly", lambda path: object())
    monkeypatch.setattr(
        "duckclaw.graphs.chat_heartbeat.publish_admin_chat_heartbeat", lambda *a, **k: None
    )


def test_auto_compaction_summarizes_and_replaces_history(monkeypatch) -> None:
    from core.chat_graph_runner import _auto_compact_history_if_needed

    monkeypatch.setenv("DUCKCLAW_CHAT_HISTORY_TOKEN_BUDGET", "10000")
    history = _msgs(40, 4000)
    tail = history[-6:]
    saved: dict = {}
    _patch_io(monkeypatch, fold_result=("resumen SNX/WOR", None, {"kept_history": tail}), saved=saved)

    new_prepared, compacted, summary = asyncio.run(
        _auto_compact_history_if_needed(_prepared(history), redis_client=object())
    )

    assert summary == "resumen SNX/WOR"
    assert compacted == tail
    assert new_prepared.history_for_model == tail
    assert new_prepared.history_for_graph == tail
    assert saved["summary"] == "resumen SNX/WOR"
    assert saved["redis"] == tail


def test_auto_compaction_noop_below_threshold(monkeypatch) -> None:
    from core.chat_graph_runner import _auto_compact_history_if_needed

    monkeypatch.setenv("DUCKCLAW_CHAT_HISTORY_TOKEN_BUDGET", "120000")
    history = _msgs(10, 100)
    prepared = _prepared(history)
    out, compacted, summary = asyncio.run(
        _auto_compact_history_if_needed(prepared, redis_client=None)
    )
    assert out is prepared and compacted is None and summary == ""


def test_auto_compaction_falls_back_to_trim_when_fold_fails(monkeypatch) -> None:
    from core.chat_graph_runner import _auto_compact_history_if_needed

    monkeypatch.setenv("DUCKCLAW_CHAT_HISTORY_TOKEN_BUDGET", "10000")
    history = _msgs(40, 4000)
    saved: dict = {}
    _patch_io(monkeypatch, fold_result=(None, "Context monitor desactivado", {}), saved=saved)

    new_prepared, compacted, summary = asyncio.run(
        _auto_compact_history_if_needed(_prepared(history), redis_client=object())
    )
    assert summary == ""
    assert "summary" not in saved
    assert compacted and compacted[-1] == history[-1]
    assert len(compacted) < len(history)


def test_document_turn_keeps_empty_graph_history(monkeypatch) -> None:
    from dataclasses import replace

    from core.chat_graph_runner import _auto_compact_history_if_needed

    monkeypatch.setenv("DUCKCLAW_CHAT_HISTORY_TOKEN_BUDGET", "10000")
    history = _msgs(40, 4000)
    saved: dict = {}
    _patch_io(monkeypatch, fold_result=("s", None, {"kept_history": history[-4:]}), saved=saved)
    prepared = replace(_prepared(history), history_for_graph=[])
    new_prepared, _, _ = asyncio.run(_auto_compact_history_if_needed(prepared, redis_client=None))
    assert new_prepared.history_for_graph == []
