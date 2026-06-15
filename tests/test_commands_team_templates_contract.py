from __future__ import annotations

import importlib
import inspect

from duckclaw.graphs import on_the_fly_commands


CANONICAL_MODULE = "duckclaw.commands.team_templates"
TEAM_TEMPLATE_EXPORTS = (
    "_tenant_team_config_key",
    "get_team_templates",
    "set_team_templates",
    "get_tenant_team_templates",
    "set_tenant_team_templates",
    "_canonicalize_team_template_ids",
    "get_effective_team_templates",
    "_resolve_template_id",
    "execute_team",
)


def test_team_templates_ownership_lives_outside_graphs() -> None:
    for name in TEAM_TEMPLATE_EXPORTS:
        exported = getattr(on_the_fly_commands, name)
        assert exported.__module__ == CANONICAL_MODULE

    team_templates = importlib.import_module(CANONICAL_MODULE)
    source = inspect.getsource(team_templates)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source


def test_on_the_fly_team_template_imports_remain_compatible() -> None:
    team_templates = importlib.import_module(CANONICAL_MODULE)

    for name in TEAM_TEMPLATE_EXPORTS:
        assert getattr(on_the_fly_commands, name) is getattr(team_templates, name)
