from __future__ import annotations

import importlib
import inspect

from duckclaw.graphs import on_the_fly_commands


CANONICAL_MODULE = "duckclaw.commands.goals"
GOALS_EXPORTS = (
    "_normalize_belief_key",
    "_get_goals_registry_fallback_first",
    "_get_goals_registry_for_chat",
    "get_manager_goals",
    "set_manager_goals",
    "_goal_title",
    "_natural_language_goal_to_params",
    "_persist_homeostasis_manifest_db",
    "_format_homeostasis_manifest_listing",
    "execute_homeostasis_goals",
)


def test_goals_command_ownership_lives_outside_graphs() -> None:
    goals = importlib.import_module(CANONICAL_MODULE)

    for name in GOALS_EXPORTS:
        exported = getattr(on_the_fly_commands, name)
        assert exported.__module__ == CANONICAL_MODULE

    source = inspect.getsource(goals)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source


def test_on_the_fly_goals_imports_remain_compatible() -> None:
    goals = importlib.import_module(CANONICAL_MODULE)

    for name in GOALS_EXPORTS:
        assert getattr(on_the_fly_commands, name) is getattr(goals, name)
