from __future__ import annotations

import importlib
import inspect

from duckclaw.graphs import on_the_fly_commands


CANONICAL_MODULE = "duckclaw.commands.fly_outbound"
FLY_OUTBOUND_EXPORTS = (
    "register_fly_outbound_chart_b64",
    "pop_all_fly_outbound_charts",
    "pop_all_fly_outbound_charts_b64",
    "pop_fly_outbound_chart_b64",
)


def test_fly_outbound_ownership_lives_outside_graphs() -> None:
    fly_outbound = importlib.import_module(CANONICAL_MODULE)

    for name in FLY_OUTBOUND_EXPORTS:
        exported = getattr(on_the_fly_commands, name)
        assert exported.__module__ == CANONICAL_MODULE

    source = inspect.getsource(fly_outbound)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source


def test_on_the_fly_fly_outbound_imports_remain_compatible() -> None:
    fly_outbound = importlib.import_module(CANONICAL_MODULE)

    for name in FLY_OUTBOUND_EXPORTS:
        assert getattr(on_the_fly_commands, name) is getattr(fly_outbound, name)
