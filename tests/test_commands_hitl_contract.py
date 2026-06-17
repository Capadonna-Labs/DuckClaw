from __future__ import annotations

import importlib
import inspect

from duckclaw.graphs import on_the_fly_commands


CANONICAL_MODULE = "duckclaw.commands.hitl"
HITL_EXPORTS = (
    "execute_resolve_uncertainty",
    "execute_code_reject",
    "execute_code_approve",
    "execute_uncertainty_status",
)


def test_hitl_command_ownership_lives_outside_graphs() -> None:
    hitl = importlib.import_module(CANONICAL_MODULE)

    for name in HITL_EXPORTS:
        exported = getattr(on_the_fly_commands, name)
        assert exported.__module__ == CANONICAL_MODULE

    source = inspect.getsource(hitl)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source


def test_hitl_module_has_no_capadonna_coupling() -> None:
    hitl = importlib.import_module(CANONICAL_MODULE)
    source = inspect.getsource(hitl).lower()

    forbidden = {
        "capadonna",
        "driller",
        "load_capadonna_lib",
        "dispatch_capadonna_fly_command",
        "epistemic_humility",
    }
    leaked = sorted(marker for marker in forbidden if marker in source)

    assert leaked == []


def test_hitl_module_has_no_vertical_runtime_defaults() -> None:
    hitl = importlib.import_module(CANONICAL_MODULE)
    source = inspect.getsource(hitl).lower()

    forbidden = {
        "capadonna",
        "driller",
        "quant",
        "trader",
        "finance",
        "platform-orchestrator",
        "ibkr",
        "pqrs",
        "pqrsd",
        "leila",
        "war room",
        "job hunter",
    }
    leaked = sorted(marker for marker in forbidden if marker in source)

    assert leaked == []


def test_hitl_commands_delegate_to_transversal_services() -> None:
    hitl = importlib.import_module(CANONICAL_MODULE)
    source = inspect.getsource(hitl)

    assert "duckclaw.hitl.code_decision_service" in source
    assert "duckclaw.hitl.uncertainty_service" in source
    assert "capadonna" not in source.lower()


def test_on_the_fly_hitl_imports_remain_compatible() -> None:
    hitl = importlib.import_module(CANONICAL_MODULE)

    for name in HITL_EXPORTS:
        assert getattr(on_the_fly_commands, name) is getattr(hitl, name)
