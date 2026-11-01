from duckclaw.manager.manager_mercenary_policy import _should_disable_mercenary_for_admin_ui


def test_worlds_think_chats_never_route_to_the_stub_mercenary():
    assert _should_disable_mercenary_for_admin_ui("world-bot_abc123")
    assert _should_disable_mercenary_for_admin_ui("admin-conv-0f0f")


def test_worlds_chats_have_the_sandbox_on_by_default(monkeypatch):
    import duckclaw.runtime_session_settings as rss
    from duckclaw.workers.factory_graph_nodes_prepare import sandbox_enabled_for_chat

    monkeypatch.setattr(rss, "resolve_session_runtime_setting", lambda *a, **k: "")
    assert sandbox_enabled_for_chat(None, "world-bot_abc", "t")
    assert not sandbox_enabled_for_chat(None, "some-other-chat", "t")
