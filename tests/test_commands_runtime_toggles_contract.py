from __future__ import annotations

import importlib
import inspect
from typing import Any

import duckclaw
from duckclaw.graphs import on_the_fly_commands


CANONICAL_MODULE = "duckclaw.commands.runtime_toggles"
RUNTIME_TOGGLE_FUNCTION_EXPORTS = (
    "execute_sandbox_toggle",
    "execute_internet_toggle",
    "configure_sandbox_session_cleanup",
)


def test_runtime_toggle_command_ownership_lives_outside_graphs() -> None:
    runtime_toggles = importlib.import_module(CANONICAL_MODULE)

    for name in RUNTIME_TOGGLE_FUNCTION_EXPORTS:
        exported = getattr(on_the_fly_commands, name)
        assert exported.__module__ == CANONICAL_MODULE
        assert exported is getattr(runtime_toggles, name)
    assert runtime_toggles.set_runtime_toggle_state.__module__ == CANONICAL_MODULE

    source = inspect.getsource(runtime_toggles)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source
    assert "duckclaw.graphs." not in source


def test_runtime_toggles_module_has_no_vertical_defaults() -> None:
    runtime_toggles = importlib.import_module(CANONICAL_MODULE)
    source = inspect.getsource(runtime_toggles).lower()

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
        "duckclaw.workers.factory",
    }
    leaked = sorted(marker for marker in forbidden if marker in source)

    assert leaked == []


def test_sandbox_toggle_state_is_chat_scoped_runtime_setting() -> None:
    runtime_toggles = importlib.import_module(CANONICAL_MODULE)
    from duckclaw.admin_runtime_settings import resolve_runtime_setting

    db = duckclaw.DuckClaw(":memory:")

    enabled = runtime_toggles.execute_sandbox_toggle(db, "chat1", "on")
    status = runtime_toggles.execute_sandbox_toggle(db, "chat1", "")
    disabled = runtime_toggles.execute_sandbox_toggle(db, "chat1", "off")
    resolved = resolve_runtime_setting(
        db,
        tenant_id="default",
        actor_email="chat:chat1",
        domain="runtime.session",
        key="sandbox_enabled",
    )

    assert "habilitado" in enabled
    assert "Estado actual: habilitado" in status
    assert "desactivado" in disabled
    assert resolved["source"] == "db"
    assert resolved["value"] == "false"


def test_runtime_toggles_do_not_write_sandbox_flags_to_agent_config() -> None:
    runtime_toggles = importlib.import_module(CANONICAL_MODULE)
    source = inspect.getsource(runtime_toggles)

    forbidden = {
        "UpsertAgentConfigEntriesCommand",
        'set_chat_state(db, chat_id, "sandbox_enabled"',
        'set_chat_state(db, chat_id, "sandbox_network_enabled"',
        'get_chat_state(db, chat_id, "sandbox_enabled"',
        'get_chat_state(db, chat_id, "sandbox_network_enabled"',
    }
    leaked = sorted(marker for marker in forbidden if marker in source)

    assert leaked == []


def test_internet_toggle_uses_explicit_cleanup_callback(monkeypatch: Any) -> None:
    runtime_toggles = importlib.import_module(CANONICAL_MODULE)
    db = duckclaw.DuckClaw(":memory:")
    cleanup_calls: list[str] = []

    monkeypatch.setattr(
        runtime_toggles,
        "resolve_sandbox_network_policy",
        lambda _wid, _raw: (None, {"toggle_available": True, "effective": "allow"}),
    )
    runtime_toggles.configure_sandbox_session_cleanup(cleanup_calls.append)
    try:
        enabled = runtime_toggles.execute_internet_toggle(
            db,
            "chat1",
            "on",
            worker_id="default",
        )
        disabled = runtime_toggles.execute_internet_toggle(
            db,
            "chat1",
            "off",
            worker_id="default",
        )
    finally:
        runtime_toggles.configure_sandbox_session_cleanup(None)

    assert "activado" in enabled
    assert "desactivado" in disabled
    assert cleanup_calls == ["chat1", "chat1"]

    from duckclaw.admin_runtime_settings import resolve_runtime_setting

    resolved = resolve_runtime_setting(
        db,
        tenant_id="default",
        actor_email="chat:chat1",
        domain="runtime.session",
        key="sandbox_network_enabled",
    )
    assert resolved["source"] == "db"
    assert resolved["value"] == "false"


def test_internet_network_aliases_remain_dispatcher_compatible(monkeypatch: Any) -> None:
    calls: list[tuple[str, str, str, str]] = []

    def _fake_internet_toggle(
        db: Any,
        chat_id: Any,
        args: str,
        *,
        worker_id: str = "",
        tenant_id: str = "default",
    ) -> str:
        del db
        calls.append((str(chat_id), args, worker_id, tenant_id))
        return "ok"

    monkeypatch.setattr(on_the_fly_commands, "execute_internet_toggle", _fake_internet_toggle)

    for alias in ("internet", "red", "network"):
        out = on_the_fly_commands._dispatch_fly_command(
            object(),
            "chat1",
            alias,
            "on",
            tenant_id="tenant1",
            entry_worker_id="worker1",
        )
        assert out == "ok"

    assert calls == [
        ("chat1", "on", "worker1", "tenant1"),
        ("chat1", "on", "worker1", "tenant1"),
        ("chat1", "on", "worker1", "tenant1"),
    ]


def test_on_the_fly_runtime_toggle_imports_remain_compatible() -> None:
    runtime_toggles = importlib.import_module(CANONICAL_MODULE)

    for name in RUNTIME_TOGGLE_FUNCTION_EXPORTS:
        assert getattr(on_the_fly_commands, name) is getattr(runtime_toggles, name)
