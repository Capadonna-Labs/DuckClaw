from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest


_GATEWAY_DIR = Path(__file__).resolve().parents[1] / "services" / "api-gateway"
if str(_GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(_GATEWAY_DIR))

MIGRATED_READ_ONLY_FLY_COMMANDS = (
    "audit",
    "crons",
    "heartbeat",
    "health",
    "history",
    "internet",
    "llm",
    "model",
    "models",
    "network",
    "prompt",
    "provider",
    "red",
    "sandbox",
    "sandox",
    "setup",
    "system",
    "system_prompt",
    "team",
    "vault",
)


def test_context_fly_command_opens_read_only_duckclaw(monkeypatch, tmp_path: Path) -> None:
    from core import fly_command_invocation

    opened: list[tuple[str, bool, str]] = []

    class FakeDuckClaw:
        def __init__(self, db_path: str, *, read_only: bool, engine: str) -> None:
            self._path = db_path
            self._read_only = read_only
            opened.append((db_path, read_only, engine))

        def close(self) -> None:
            pass

    def fake_handle_command(
        db: Any,
        chat_id: Any,
        text: str,
        **_kwargs: Any,
    ) -> str:
        assert text == "/context on"
        assert getattr(db, "_read_only", False) is True
        return "context ok"

    monkeypatch.setattr(fly_command_invocation, "DuckClaw", FakeDuckClaw)
    monkeypatch.setattr(fly_command_invocation, "handle_command", fake_handle_command)
    monkeypatch.setattr(fly_command_invocation, "_attach_fly_charts", lambda *_args, **_kwargs: None)

    vault_path = tmp_path / "vault.duckdb"
    response = asyncio.run(
        fly_command_invocation.invoke_legacy_fly_command(
            message="/context on",
            session_id="chat1",
            worker_id="manager",
            tenant_id="tenant-a",
            vault_db_path=str(vault_path),
            vault_user_id="user-a",
            requester_id="requester-a",
            username="ana",
            delivery_context=SimpleNamespace(channel="http", outbound_bot_token=""),
            resolve_telegram_bot_token=lambda: "",
            persist_admin_fly_charts=lambda *_args: [],
        )
    )

    assert response is not None
    assert response["response"] == "context ok"
    assert opened == [(str(vault_path), True, "python")]


def test_workers_fly_command_is_read_only_safe_after_db_first_migration() -> None:
    from core import fly_command_invocation

    assert "workers" in fly_command_invocation.READ_ONLY_SAFE_FLY_COMMANDS
    assert "workers" not in fly_command_invocation.LEGACY_RW_FLY_COMMANDS


def test_forget_fly_command_is_read_only_safe_after_db_first_migration() -> None:
    from core import fly_command_invocation

    assert "forget" in fly_command_invocation.READ_ONLY_SAFE_FLY_COMMANDS
    assert "forget" not in fly_command_invocation.LEGACY_RW_FLY_COMMANDS


@pytest.mark.parametrize("command_name", MIGRATED_READ_ONLY_FLY_COMMANDS)
def test_db_first_fly_command_batch_is_read_only_safe(command_name: str) -> None:
    from core import fly_command_invocation

    assert command_name in fly_command_invocation.READ_ONLY_SAFE_FLY_COMMANDS
    assert command_name not in fly_command_invocation.LEGACY_RW_FLY_COMMANDS


@pytest.mark.parametrize("command_name", MIGRATED_READ_ONLY_FLY_COMMANDS)
def test_db_first_fly_command_batch_opens_read_only_duckclaw(
    command_name: str,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from core import fly_command_invocation

    opened: list[tuple[str, bool, str]] = []

    class FakeDuckClaw:
        def __init__(self, db_path: str, *, read_only: bool, engine: str) -> None:
            self._path = db_path
            self._read_only = read_only
            opened.append((db_path, read_only, engine))

        def close(self) -> None:
            pass

    def fake_handle_command(
        db: Any,
        chat_id: Any,
        text: str,
        **_kwargs: Any,
    ) -> str:
        assert chat_id == "chat1"
        assert text == f"/{command_name}"
        assert getattr(db, "_read_only", False) is True
        return f"{command_name} ok"

    monkeypatch.setattr(fly_command_invocation, "DuckClaw", FakeDuckClaw)
    monkeypatch.setattr(fly_command_invocation, "handle_command", fake_handle_command)
    monkeypatch.setattr(fly_command_invocation, "_attach_fly_charts", lambda *_args, **_kwargs: None)

    vault_path = tmp_path / "vault.duckdb"
    response = asyncio.run(
        fly_command_invocation.invoke_legacy_fly_command(
            message=f"/{command_name}",
            session_id="chat1",
            worker_id="manager",
            tenant_id="tenant-a",
            vault_db_path=str(vault_path),
            vault_user_id="user-a",
            requester_id="requester-a",
            username="ana",
            delivery_context=SimpleNamespace(channel="http", outbound_bot_token=""),
            resolve_telegram_bot_token=lambda: "",
            persist_admin_fly_charts=lambda *_args: [],
        )
    )

    assert response is not None
    assert response["response"] == f"{command_name} ok"
    assert opened == [(str(vault_path), True, "python")]


def test_workers_fly_command_opens_read_only_duckclaw(monkeypatch, tmp_path: Path) -> None:
    from core import fly_command_invocation

    opened: list[tuple[str, bool, str]] = []

    class FakeDuckClaw:
        def __init__(self, db_path: str, *, read_only: bool, engine: str) -> None:
            self._path = db_path
            self._read_only = read_only
            opened.append((db_path, read_only, engine))

        def close(self) -> None:
            pass

    def fake_handle_command(
        db: Any,
        chat_id: Any,
        text: str,
        **_kwargs: Any,
    ) -> str:
        assert text == "/workers alpha"
        assert getattr(db, "_read_only", False) is True
        return "workers ok"

    monkeypatch.setattr(fly_command_invocation, "DuckClaw", FakeDuckClaw)
    monkeypatch.setattr(fly_command_invocation, "handle_command", fake_handle_command)
    monkeypatch.setattr(fly_command_invocation, "_attach_fly_charts", lambda *_args, **_kwargs: None)

    vault_path = tmp_path / "vault.duckdb"
    response = asyncio.run(
        fly_command_invocation.invoke_legacy_fly_command(
            message="/workers alpha",
            session_id="chat1",
            worker_id="manager",
            tenant_id="tenant-a",
            vault_db_path=str(vault_path),
            vault_user_id="user-a",
            requester_id="requester-a",
            username="ana",
            delivery_context=SimpleNamespace(channel="http", outbound_bot_token=""),
            resolve_telegram_bot_token=lambda: "",
            persist_admin_fly_charts=lambda *_args: [],
        )
    )

    assert response is not None
    assert response["response"] == "workers ok"
    assert opened == [(str(vault_path), True, "python")]


def test_forget_fly_command_opens_read_only_duckclaw(monkeypatch, tmp_path: Path) -> None:
    from core import fly_command_invocation

    opened: list[tuple[str, bool, str]] = []

    class FakeDuckClaw:
        def __init__(self, db_path: str, *, read_only: bool, engine: str) -> None:
            self._path = db_path
            self._read_only = read_only
            opened.append((db_path, read_only, engine))

        def close(self) -> None:
            pass

    def fake_handle_command(
        db: Any,
        chat_id: Any,
        text: str,
        **_kwargs: Any,
    ) -> str:
        assert text == "/forget"
        assert getattr(db, "_read_only", False) is True
        return "✅ Historial borrado."

    monkeypatch.setattr(fly_command_invocation, "DuckClaw", FakeDuckClaw)
    monkeypatch.setattr(fly_command_invocation, "handle_command", fake_handle_command)
    monkeypatch.setattr(fly_command_invocation, "_attach_fly_charts", lambda *_args, **_kwargs: None)

    vault_path = tmp_path / "vault.duckdb"
    response = asyncio.run(
        fly_command_invocation.invoke_legacy_fly_command(
            message="/forget",
            session_id="chat1",
            worker_id="manager",
            tenant_id="tenant-a",
            vault_db_path=str(vault_path),
            vault_user_id="user-a",
            requester_id="requester-a",
            username="ana",
            delivery_context=SimpleNamespace(channel="http", outbound_bot_token=""),
            resolve_telegram_bot_token=lambda: "",
            persist_admin_fly_charts=lambda *_args: [],
        )
    )

    assert response is not None
    assert response["response"] == "✅ Historial borrado."
    assert opened == [(str(vault_path), True, "python")]
