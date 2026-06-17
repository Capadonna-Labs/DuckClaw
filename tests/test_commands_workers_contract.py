from __future__ import annotations

import importlib
import inspect

from duckclaw.graphs import on_the_fly_commands


CANONICAL_MODULE = "duckclaw.commands.workers"
WORKERS_FUNCTION_EXPORTS = (
    "execute_roles",
    "execute_skills_list",
)
WORKERS_CONSTANT_EXPORTS = ("_DEFAULT_WORKER",)


def test_workers_command_ownership_lives_outside_graphs() -> None:
    workers = importlib.import_module(CANONICAL_MODULE)

    for name in WORKERS_FUNCTION_EXPORTS:
        exported = getattr(on_the_fly_commands, name)
        assert exported.__module__ == CANONICAL_MODULE

    source = inspect.getsource(workers)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source


def test_on_the_fly_workers_imports_remain_compatible() -> None:
    workers = importlib.import_module(CANONICAL_MODULE)

    for name in WORKERS_FUNCTION_EXPORTS:
        assert getattr(on_the_fly_commands, name) is getattr(workers, name)
    for name in WORKERS_CONSTANT_EXPORTS:
        assert getattr(on_the_fly_commands, name) == getattr(workers, name)
