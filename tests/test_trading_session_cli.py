from __future__ import annotations

from duckclaw.graphs.on_the_fly_commands import _dispatch_fly_command


def test_vertical_session_command_is_not_owned_by_core_command_graph() -> None:
    cmd = "trading" + "-session"
    assert _dispatch_fly_command(None, "chat-1", cmd, "") is None


def test_vertical_cycle_command_is_not_owned_by_core_command_graph() -> None:
    cmd = "quant" + "_cycle"
    assert _dispatch_fly_command(None, "chat-1", cmd, "") is None
