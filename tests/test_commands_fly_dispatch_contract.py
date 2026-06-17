from __future__ import annotations

import importlib
import inspect

from duckclaw.graphs import on_the_fly_commands


CANONICAL_MODULE = "duckclaw.commands.fly_dispatch"
FLY_DISPATCH_EXPORTS = (
    "parse_command",
    "handle_command",
    "get_worker_id_for_chat",
    "_dispatch_fly_command",
)


def test_fly_dispatch_ownership_lives_outside_graphs() -> None:
    fly_dispatch = importlib.import_module(CANONICAL_MODULE)

    for name in FLY_DISPATCH_EXPORTS:
        exported = getattr(on_the_fly_commands, name)
        assert exported.__module__ == CANONICAL_MODULE

    source = inspect.getsource(fly_dispatch)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source


def test_on_the_fly_fly_dispatch_imports_remain_compatible() -> None:
    fly_dispatch = importlib.import_module(CANONICAL_MODULE)

    for name in FLY_DISPATCH_EXPORTS:
        assert getattr(on_the_fly_commands, name) is getattr(fly_dispatch, name)
