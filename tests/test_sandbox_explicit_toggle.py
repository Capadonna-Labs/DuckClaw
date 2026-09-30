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
