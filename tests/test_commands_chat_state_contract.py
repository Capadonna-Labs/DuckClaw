from __future__ import annotations

import inspect

from duckclaw.commands import chat_state
from duckclaw.graphs import on_the_fly_commands


def test_chat_state_ownership_lives_outside_graphs() -> None:
    assert chat_state.get_chat_state.__module__ == "duckclaw.commands.chat_state"
    assert chat_state.set_chat_state.__module__ == "duckclaw.commands.chat_state"
    assert chat_state._ensure_agent_config.__module__ == "duckclaw.commands.chat_state"

    source = inspect.getsource(chat_state)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source


def test_on_the_fly_chat_state_imports_remain_compatible() -> None:
    assert on_the_fly_commands.get_chat_state is chat_state.get_chat_state
    assert on_the_fly_commands.set_chat_state is chat_state.set_chat_state
    assert on_the_fly_commands._ensure_agent_config is chat_state._ensure_agent_config
    assert on_the_fly_commands._chat_key is chat_state._chat_key
    assert on_the_fly_commands._skip_runtime_ddl is chat_state._skip_runtime_ddl

