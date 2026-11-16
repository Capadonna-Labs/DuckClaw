"""Suggestions Auto countdown seconds: per-chat, clamped, unset = None (UI default)."""

from duckclaw.commands import suggestions_auto as sa


def test_clamp_and_read(monkeypatch):
    state = {}
    monkeypatch.setattr(sa, "get_chat_state", lambda db, chat, key: state.get(key, ""))
    monkeypatch.setattr(sa, "set_chat_state_via_typed_command",
                        lambda db, chat, key, value, tenant_id="default": (state.__setitem__(key, value), (True, ""))[1])
    assert sa.suggestions_auto_seconds(None, "c") is None
    assert sa.set_suggestions_auto_seconds(None, "c", 8) == (True, "")
    assert sa.suggestions_auto_seconds(None, "c") == 8
    assert sa.clamp_auto_seconds(0) == 3 and sa.clamp_auto_seconds(9999) == 300 and sa.clamp_auto_seconds("x") == 15
