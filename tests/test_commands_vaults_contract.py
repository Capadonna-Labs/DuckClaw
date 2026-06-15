from __future__ import annotations

import importlib
import inspect

from duckclaw.graphs import on_the_fly_commands


CANONICAL_MODULE = "duckclaw.commands.vaults"
VAULT_EXPORTS = (
    "_dedicated_gateway_db_path_for_vault",
    "_session_duckdb_path_for_fly",
    "_fly_vault_label_for_tenant",
    "_dedicated_gateway_vault_label",
    "_format_vault_size_mb",
    "_effective_vault_tenant_label",
    "_template_bound_vault_path",
    "execute_vault",
)


def test_vault_command_ownership_lives_outside_graphs() -> None:
    for name in VAULT_EXPORTS:
        exported = getattr(on_the_fly_commands, name)
        assert exported.__module__ == CANONICAL_MODULE

    vaults = importlib.import_module(CANONICAL_MODULE)
    source = inspect.getsource(vaults)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source


def test_on_the_fly_vault_imports_remain_compatible() -> None:
    vaults = importlib.import_module(CANONICAL_MODULE)

    for name in VAULT_EXPORTS:
        assert getattr(on_the_fly_commands, name) is getattr(vaults, name)
