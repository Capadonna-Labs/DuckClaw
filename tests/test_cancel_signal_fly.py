from __future__ import annotations

from duckclaw.graphs.on_the_fly_commands import _dispatch_fly_command


def test_cancel_signal_is_not_owned_by_core_command_graph() -> None:
    assert _dispatch_fly_command(None, "chat-1", "cancel_signal", "00000000-0000-4000-8000-000000000000") is None


def test_execute_signal_is_not_owned_by_core_command_graph() -> None:
    assert _dispatch_fly_command(None, "chat-1", "execute-signal", "00000000-0000-4000-8000-000000000000") is None
