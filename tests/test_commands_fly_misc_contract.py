from __future__ import annotations

import importlib
import inspect

from duckclaw.graphs import on_the_fly_commands


CANONICAL_MODULE = "duckclaw.commands.fly_misc"
FLY_MISC_EXPORTS = (
    "execute_tasks",
    "execute_help",
    "execute_lake_status",
    "execute_approve_reject",
)


def test_fly_misc_ownership_lives_outside_graphs() -> None:
    fly_misc = importlib.import_module(CANONICAL_MODULE)

    for name in FLY_MISC_EXPORTS:
        exported = getattr(on_the_fly_commands, name)
        assert exported.__module__ == CANONICAL_MODULE

    source = inspect.getsource(fly_misc)
    assert "duckclaw.graphs.on_the_fly_commands" not in source


def test_fly_misc_only_imports_graph_activity_for_tasks() -> None:
    fly_misc = importlib.import_module(CANONICAL_MODULE)
    source = inspect.getsource(fly_misc)

    assert "duckclaw.graphs.activity" in source
    assert "from duckclaw.graphs" in source


def test_on_the_fly_fly_misc_imports_remain_compatible() -> None:
    fly_misc = importlib.import_module(CANONICAL_MODULE)

    for name in FLY_MISC_EXPORTS:
        assert getattr(on_the_fly_commands, name) is getattr(fly_misc, name)
