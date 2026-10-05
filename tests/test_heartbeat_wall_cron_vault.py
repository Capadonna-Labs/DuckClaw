"""Clock cron prompts must run against the vault the chat state was read from.

Regression: the wall-cron payload had no vault_db_path, so the gateway resolved a
per-chat-id vault (db/private/<chat>/default.duckdb) and the worker saw an empty DB.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import pytest

import services.heartbeat.main as heartbeat


def test_wall_cron_prompt_posts_the_scanned_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    vault = "/data/private/owner1/worker_db.duckdb"
    state = {"worker_id": "worker_a", heartbeat._GOALS_PROACTIVE_TENANT_KEY: "tenant-x"}
    posted: list[dict[str, Any]] = []

    monkeypatch.setattr(heartbeat, "duckclaw_open_for_read_scan", lambda _p: contextlib.nullcontext(object()))
    monkeypatch.setattr(heartbeat, "get_chat_state", lambda _db, _cid, key: state.get(key, ""))
    monkeypatch.setattr(heartbeat, "get_manifest_goals_for_chat", lambda *_a, **_k: [])
    monkeypatch.setattr(heartbeat, "get_manager_goals", lambda *_a, **_k: [])
    monkeypatch.setattr(heartbeat, "wall_schedule_should_fire", lambda *_a, **_k: True)
    monkeypatch.setattr(heartbeat, "_scheduled_prompt_message", lambda prompt, _t: f"[DIRECTIVA] {prompt}")

    async def _noop(**_kw: Any) -> None:
        return None

    monkeypatch.setattr(heartbeat, "_send_web_push_notification", _noop)
    monkeypatch.setattr(heartbeat, "_enqueue_chat_state_write", _noop)

    class _Resp:
        status_code = 200
        text = "{}"

    class _Client:
        async def __aenter__(self) -> "_Client":
            return self

        async def __aexit__(self, *exc: Any) -> None:
            return None

        async def post(self, _url: str, *, json: dict[str, Any], **_kw: Any) -> _Resp:
            posted.append(json)
            return _Resp()

    monkeypatch.setattr(heartbeat.httpx, "AsyncClient", lambda *a, **k: _Client())

    asyncio.run(
        heartbeat._run_wall_items_for_chat(
            vault,
            "admin-conv-1",
            [{"id": "c1", "kind": "daily", "prompt": "/apertura"}],
            now=1_800_000_000.0,
            wall_poll=45.0,
            headers={},
        )
    )

    assert len(posted) == 1
    assert posted[0]["vault_db_path"] == vault
    assert posted[0]["user_incoming"] == "[Cron] /apertura"


def test_hub_is_never_sent_as_worker_vault(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    hub = tmp_path / "hub.duckdb"
    monkeypatch.setattr(heartbeat, "get_gateway_db_path", lambda: str(hub))
    payload: dict[str, Any] = {}
    heartbeat._attach_scanned_vault(payload, str(hub))
    assert "vault_db_path" not in payload
    heartbeat._attach_scanned_vault(payload, str(tmp_path / "private" / "u1" / "w.duckdb"))
    assert payload["vault_db_path"].endswith("w.duckdb")
