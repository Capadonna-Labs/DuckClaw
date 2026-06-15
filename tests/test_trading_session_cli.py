from __future__ import annotations

from duckclaw.graphs.on_the_fly_commands import _dispatch_fly_command


def test_trading_session_command_is_not_owned_by_core_command_graph() -> None:
    assert _dispatch_fly_command(None, "chat-1", "trading-session", "") is None


def test_quant_cycle_command_is_not_owned_by_core_command_graph() -> None:
    assert _dispatch_fly_command(None, "chat-1", "quant_cycle", "") is None
