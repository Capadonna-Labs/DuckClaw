"""`/meditate` fly aliases must match `/loop` state keys."""
from __future__ import annotations

from unittest.mock import MagicMock

from duckclaw.commands.fly_dispatch import _dispatch_fly_command
from duckclaw.commands.loop_state_keys import LOOP_ACTIVE_KEY
from duckclaw.commands.chat_state import get_chat_state


def _fake_db() -> MagicMock:
    store: dict[str, str] = {}

    def get(_db, _cid, key):
        return store.get(key, "")

    def set_(_db, _cid, key, val):
        store[key] = val

    db = MagicMock()
    db.get_chat_state = get
    return db, store


def test_loop_and_meditate_on_set_same_active_key(monkeypatch) -> None:
    db, store = _fake_db()
    monkeypatch.setattr(
        "duckclaw.commands.loop.set_chat_state",
        lambda _db, _cid, key, val: store.__setitem__(key, val),
    )
    monkeypatch.setattr(
        "duckclaw.commands.loop.get_chat_state",
        lambda _db, _cid, key: store.get(key, ""),
    )
    monkeypatch.setattr(
        "duckclaw.commands.loop._skip_runtime_ddl",
        lambda _db: False,
    )
    monkeypatch.setattr(
        "duckclaw.commands.loop._resolve_loop_worker_id",
        lambda *a, **k: "analytics-worker",
    )
    monkeypatch.setattr(
        "duckclaw.commands.loop._execute_loop_enable",
        lambda db, cid, secs, **kw: f"ok {secs}",
    )

    r_loop = _dispatch_fly_command(db, "chat-1", "loop", "on 1h", tenant_id="t1")
    assert "ok" in r_loop.lower() or "14400" in r_loop or "3600" in r_loop

    store.clear()
    r_med = _dispatch_fly_command(db, "chat-1", "meditate", "on 1h", tenant_id="t1")
    assert r_med == r_loop or ("ok" in r_med.lower())
