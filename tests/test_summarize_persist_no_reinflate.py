"""Regression: /summarize must not reinflate Redis via fat history_for_model."""

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


def test_persist_uses_compacted_history_base(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.chat_history_persist import persist_chat_history

    saved: dict[str, Any] = {}

    async def _fake_redis_save(_redis, tenant_id, session_id, items):
        saved["tenant_id"] = tenant_id
        saved["session_id"] = session_id
        saved["items"] = items

    async def _fake_upsert(*_a, **_k):
        return None

    async def _fake_touch(*_a, **_k):
        return None

    monkeypatch.setattr("core.chat_history_persist.redis_save_chat_history", _fake_redis_save)
    monkeypatch.setattr("core.chat_history_persist.upsert_conversation_meta", _fake_upsert)
    monkeypatch.setattr("core.chat_history_persist.gateway_chat_history_enabled", lambda: True)
    monkeypatch.setattr(
        "core.chat_history_persist._touch_loop_activity_if_configured",
        _fake_touch,
    )

    fat = [{"role": "user", "content": "old" * 50}, {"role": "assistant", "content": "fat" * 50}]
    compact = [{"role": "user", "content": "kept"}, {"role": "assistant", "content": "short"}]
    prepared = SimpleNamespace(
        tenant_id="default",
        session_id="chat-1",
        is_system_prompt=False,
        user_incoming="/summarize",
        worker_id="quant_analyst",
        vault_db_path="",
        message="/summarize",
    )

    asyncio.run(
        persist_chat_history(
            prepared=prepared,
            redis_client=object(),
            reply_plain_for_storage="✅ compactado",
            effective_worker_id="quant_analyst",
            history_for_model=compact,  # finalize should pass compacted, not fat
            message="/summarize",
            username="admin",
        )
    )
    assert saved["items"][0] == compact[0]
    assert saved["items"][1] == compact[1]
    assert saved["items"][-2]["content"] == "/summarize"
    assert "compactado" in saved["items"][-1]["content"]
    assert len(saved["items"]) == 4
    assert all(item not in saved["items"] for item in fat)
