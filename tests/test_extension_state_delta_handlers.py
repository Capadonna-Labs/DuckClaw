"""Unit tests for extension StateDelta handler registry."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from duckclaw.extensions.manifest import StateDeltaHandlerEntry, _parse_state_delta_handlers
from duckclaw.extensions.state_delta import (
    _resolve_queue_name,
    load_state_delta_handler_bindings,
)


def test_parse_state_delta_handlers_from_yaml_shape() -> None:
    raw = [
        {
            "queue_env": "MY_QUEUE_ENV",
            "default_queue": "duckclaw:state_delta:example",
            "entrypoint": "example_handler:handle_message",
            "lib_path": "plugins/db_writer",
        }
    ]
    entries = _parse_state_delta_handlers(raw)
    assert len(entries) == 1
    assert entries[0].queue_env == "MY_QUEUE_ENV"
    assert entries[0].default_queue == "duckclaw:state_delta:example"
    assert entries[0].entrypoint == "example_handler:handle_message"
    assert entries[0].lib_path == "plugins/db_writer"


def test_resolve_queue_name_prefers_env() -> None:
    entry = StateDeltaHandlerEntry(
        entrypoint="mod:fn",
        queue_env="TEST_QUEUE_ENV",
        default_queue="fallback-queue",
    )
    monkeypatch = pytest.MonkeyPatch()
    try:
        monkeypatch.setenv("TEST_QUEUE_ENV", "resolved-from-env")
        assert _resolve_queue_name(entry) == "resolved-from-env"
    finally:
        monkeypatch.undo()


def test_resolve_queue_name_uses_literal_queue() -> None:
    entry = StateDeltaHandlerEntry(
        entrypoint="mod:fn",
        queue="literal-queue",
    )
    assert _resolve_queue_name(entry) == "literal-queue"


def test_load_bindings_from_env_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handler_file = tmp_path / "ext_lib" / "demo_handler.py"
    handler_file.parent.mkdir(parents=True)
    handler_file.write_text(
        """
import asyncio

async def handle_demo_message(redis_client, message: str) -> None:
    return None
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("DUCKCLAW_EXTENSION_ROOT", str(tmp_path))
    monkeypatch.setenv(
        "DUCKCLAW_EXTRA_STATE_DELTA_HANDLERS",
        json.dumps(
            [
                {
                    "queue": "duckclaw:state_delta:demo",
                    "entrypoint": "demo_handler:handle_demo_message",
                    "lib_path": "ext_lib",
                }
            ]
        ),
    )
    monkeypatch.delenv("DUCKCLAW_FLY_MANIFEST", raising=False)

    bindings = load_state_delta_handler_bindings()
    assert len(bindings) == 1
    assert bindings[0].queue_name == "duckclaw:state_delta:demo"
    assert bindings[0].handler is not None
