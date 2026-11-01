from duckclaw.manager.manager_mercenary_policy import _should_disable_mercenary_for_admin_ui


def test_worlds_think_chats_never_route_to_the_stub_mercenary():
    assert _should_disable_mercenary_for_admin_ui("world-bot_abc123")
    assert _should_disable_mercenary_for_admin_ui("admin-conv-0f0f")
