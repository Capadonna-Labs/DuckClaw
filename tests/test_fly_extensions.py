"""Tests for generic external fly command extensions."""

from __future__ import annotations

import textwrap
from pathlib import Path

import duckclaw
import pytest

from duckclaw.commands.fly_dispatch import handle_command
from duckclaw.extensions.fly import (
    dispatch_extension_fly_command,
    extension_fly_read_only_command_names,
    invalidate_extension_fly_cache,
)


@pytest.fixture
def extension_sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    lib = tmp_path / "lib"
    lib.mkdir(parents=True)
    (lib / "__init__.py").write_text("", encoding="utf-8")
    (lib / "fake_fly.py").write_text(
        textwrap.dedent(
            """
            def dispatch(name, db, chat_id, args, **kwargs):
                if name in ("fake", "fake-cmd"):
                    return f"fake-ok:{args}"
                return None
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    manifest = tmp_path / "fly_extension.yaml"
    manifest.write_text(
        textwrap.dedent(
            f"""
            lib_path: lib
            package_name: test_ext_pkg
            fly_dispatchers:
              - fake_fly:dispatch
            read_only_commands:
              - fake-cmd
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DUCKCLAW_EXTENSION_ROOT", str(tmp_path))
    monkeypatch.setenv("DUCKCLAW_FLY_MANIFEST", str(manifest))
    monkeypatch.delenv("DUCKCLAW_FLY_DISPATCHERS", raising=False)
    monkeypatch.delenv("DUCKCLAW_FLY_READ_ONLY_EXTRA", raising=False)
    invalidate_extension_fly_cache()
    yield tmp_path
    invalidate_extension_fly_cache()


def test_extension_dispatch_returns_response(extension_sandbox: Path) -> None:
    db = duckclaw.DuckClaw(":memory:")
    out = dispatch_extension_fly_command("fake", db, "chat-ext", "hello")
    assert out == "fake-ok:hello"


def test_handle_command_routes_external_fly(extension_sandbox: Path) -> None:
    db = duckclaw.DuckClaw(":memory:")
    reply = handle_command(db, "chat-ext", "/fake ping")
    assert reply == "fake-ok:ping"


def test_read_only_commands_from_manifest(extension_sandbox: Path) -> None:
    names = extension_fly_read_only_command_names()
    assert "fake-cmd" in names
    assert "fake_cmd" in names


def test_env_only_dispatcher(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    lib = tmp_path / "plugins"
    lib.mkdir()
    (lib / "env_fly.py").write_text(
        "def dispatch(name, db, chat_id, args, **kwargs):\n"
        "    return 'env-hit' if name == 'envfly' else None\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DUCKCLAW_EXTENSION_ROOT", str(tmp_path))
    monkeypatch.setenv("DUCKCLAW_EXTENSION_LIB_PATH", "plugins")
    monkeypatch.setenv("DUCKCLAW_FLY_DISPATCHERS", "env_fly:dispatch")
    monkeypatch.setenv("DUCKCLAW_FLY_READ_ONLY_EXTRA", "envfly")
    monkeypatch.delenv("DUCKCLAW_FLY_MANIFEST", raising=False)
    invalidate_extension_fly_cache()
    db = duckclaw.DuckClaw(":memory:")
    assert handle_command(db, "c1", "/envfly") == "env-hit"
    assert "envfly" in extension_fly_read_only_command_names()
    invalidate_extension_fly_cache()
