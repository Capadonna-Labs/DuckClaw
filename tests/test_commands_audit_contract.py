from __future__ import annotations

import importlib
import inspect

from duckclaw.graphs import on_the_fly_commands


CANONICAL_MODULE = "duckclaw.commands.audit"
AUDIT_EXPORTS = (
    "execute_audit",
    "save_last_audit",
)


def test_audit_command_ownership_lives_outside_graphs() -> None:
    audit = importlib.import_module(CANONICAL_MODULE)

    for name in AUDIT_EXPORTS:
        exported = getattr(on_the_fly_commands, name)
        assert exported.__module__ == CANONICAL_MODULE

    source = inspect.getsource(audit)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source


def test_audit_module_has_no_vertical_runtime_defaults_or_rw_duckdb() -> None:
    audit = importlib.import_module(CANONICAL_MODULE)
    source = inspect.getsource(audit).lower()

    forbidden = {
        "quant",
        "trader",
        "finance",
        "finanz",
        "ibkr",
        "pqrs",
        "pqrsd",
        "leila",
        "war room",
        "job hunter",
        "read_only=false",
        "duckdb.connect",
    }
    leaked = sorted(marker for marker in forbidden if marker in source)

    assert leaked == []


def test_on_the_fly_audit_imports_remain_compatible() -> None:
    audit = importlib.import_module(CANONICAL_MODULE)

    for name in AUDIT_EXPORTS:
        assert getattr(on_the_fly_commands, name) is getattr(audit, name)
