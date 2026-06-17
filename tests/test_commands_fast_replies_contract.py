from __future__ import annotations

import importlib
import inspect

from duckclaw.graphs import on_the_fly_commands


CANONICAL_MODULE = "duckclaw.commands.fast_replies"
FAST_REPLIES_EXPORTS = ("_is_capabilities_smalltalk",)


def test_fast_replies_command_ownership_lives_outside_graphs() -> None:
    fast_replies = importlib.import_module(CANONICAL_MODULE)

    for name in FAST_REPLIES_EXPORTS:
        exported = getattr(on_the_fly_commands, name)
        assert exported.__module__ == CANONICAL_MODULE

    source = inspect.getsource(fast_replies)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source


def test_fast_replies_module_has_no_vertical_runtime_defaults() -> None:
    fast_replies = importlib.import_module(CANONICAL_MODULE)
    source = inspect.getsource(fast_replies).lower()

    forbidden = {
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


def test_is_capabilities_smalltalk_matches_meta_questions() -> None:
    fast_replies = importlib.import_module(CANONICAL_MODULE)
    detect = fast_replies._is_capabilities_smalltalk

    assert detect("¿Qué puedes hacer?")
    assert detect("qué sabes hacer")
    assert detect("What can you do?")
    assert detect("Dame un ejemplo de lo que puedes hacer")
    assert detect("muéstrame un ejemplo")


def test_is_capabilities_smalltalk_rejects_commands_concrete_tasks_and_long_text() -> None:
    fast_replies = importlib.import_module(CANONICAL_MODULE)
    detect = fast_replies._is_capabilities_smalltalk

    assert not detect("/help")
    assert not detect("")
    assert not detect("Analiza mis ventas en DuckDB y dime qué puedes hacer con esos datos")
    assert not detect("x" * 121)


def test_on_the_fly_fast_replies_imports_remain_compatible() -> None:
    fast_replies = importlib.import_module(CANONICAL_MODULE)

    for name in FAST_REPLIES_EXPORTS:
        assert getattr(on_the_fly_commands, name) is getattr(fast_replies, name)
