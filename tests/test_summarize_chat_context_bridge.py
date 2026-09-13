"""Tests for summarize_chat_context always-on tool."""

from __future__ import annotations

import json
from typing import Any

import pytest

from duckclaw.forge.skills.chat_history_compact_context import take_compacted_chat_history
from duckclaw.forge.skills.summarize_chat_context_bridge import (
    register_summarize_chat_context_skill,
    summarize_chat_context_impl,
)


def test_register_summarize_chat_context_skill_appends_tool() -> None:
    tools: list = []
    register_summarize_chat_context_skill(tools, db=None)
    assert len(tools) == 1
    assert tools[0].name == "summarize_chat_context"


def test_summarize_chat_context_in_core_pack_catalog() -> None:
    from duckclaw.workers.tool_pack_catalog import (
        clear_runtime_tool_pack_catalog_cache,
        load_default_runtime_tool_pack_catalog,
    )

    clear_runtime_tool_pack_catalog_cache()
    catalog = load_default_runtime_tool_pack_catalog()
    assert catalog.packs_for_tool("summarize_chat_context") == frozenset({"core"})


def test_summarize_chat_context_requires_chat_id(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.forge.skills import goals_tool_context as gtc

    monkeypatch.setattr(gtc, "get_goals_tool_chat_id", lambda: "")
    out = json.loads(summarize_chat_context_impl())
    assert out["status"] == "error"
    assert "chat_id" in out["error"]


def test_summarize_chat_context_impl_compacts_and_sets_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.forge.skills import goals_tool_context as gtc
    from duckclaw.forge.skills import summarize_chat_context_bridge as bridge

    monkeypatch.setattr(gtc, "get_goals_tool_chat_id", lambda: "admin-conv-test")
    monkeypatch.setattr(gtc, "get_goals_tool_tenant_id", lambda: "default")
    monkeypatch.setattr(gtc, "get_goals_tool_worker_id", lambda: "quant_analyst")
    monkeypatch.setattr(gtc, "get_goals_tool_db_path", lambda: "/tmp/vault.duckdb")
    monkeypatch.setattr(bridge, "_resolve_history_session_id", lambda cid: cid)

    fat = [
        {"role": "user", "content": "msg1"},
        {"role": "assistant", "content": "a1" * 200},
        {"role": "user", "content": "msg2"},
        {"role": "assistant", "content": "a2" * 200},
    ]
    kept = [
        {"role": "user", "content": "resumen"},
        {"role": "assistant", "content": "corto"},
    ]
    monkeypatch.setattr(bridge, "load_gateway_chat_history_sync", lambda *_a, **_k: fat)

    def _fake_fold(*_a: Any, **_k: Any) -> tuple[str, None, dict[str, Any]]:
        return (
            "fold summary body",
            None,
            {
                "kept_history": kept,
                "context_estimated_tokens": 120,
                "summary_for_vault": "fold summary body",
            },
        )

    monkeypatch.setattr(
        "duckclaw.commands.context_summarize.run_manual_context_fold",
        _fake_fold,
    )
    saved: dict[str, Any] = {}

    def _fake_save(tenant_id: str, session_id: str, items: list) -> bool:
        saved["tenant_id"] = tenant_id
        saved["session_id"] = session_id
        saved["items"] = items
        return True

    monkeypatch.setattr(bridge, "save_gateway_chat_history_sync", _fake_save)
    monkeypatch.setattr(
        "duckclaw.commands.context_fold_store.save_context_fold_summary",
        lambda *_a, **_k: True,
    )

    take_compacted_chat_history()  # clear
    out = json.loads(summarize_chat_context_impl(reason="too fat"))
    assert out["status"] == "ok"
    assert out["messages_before"] == 4
    assert out["messages_kept"] == 2
    assert out["reason"] == "too fat"
    assert saved["items"] == kept
    assert take_compacted_chat_history() == kept
