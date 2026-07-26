"""effective_hub_read_only: spawn/lite hub must not open RO connections."""

from __future__ import annotations

from pathlib import Path


def test_effective_hub_read_only_spawn_inline(tmp_path, monkeypatch) -> None:
    hub = tmp_path / "hub.duckdb"
    hub.write_bytes(b"")
    other = tmp_path / "vault.duckdb"
    other.write_bytes(b"")

    monkeypatch.setenv("DUCKCLAW_GATEWAY_DB_PATH", str(hub))
    monkeypatch.setenv("DUCKCLAW_SPAWN_PROFILE", "1")

    from duckclaw.spawn_profile import effective_hub_read_only

    assert effective_hub_read_only(str(hub), True) is False
    assert effective_hub_read_only(str(other), True) is True
    assert effective_hub_read_only(str(hub), False) is False


def test_effective_hub_read_only_non_spawn(tmp_path, monkeypatch) -> None:
    hub = tmp_path / "hub.duckdb"
    hub.write_bytes(b"")
    monkeypatch.setenv("DUCKCLAW_GATEWAY_DB_PATH", str(hub))
    monkeypatch.delenv("DUCKCLAW_SPAWN_PROFILE", raising=False)
    monkeypatch.delenv("LITE_MODE", raising=False)
    monkeypatch.delenv("DUCKCLAW_SPAWN_USE_DB_WRITER", raising=False)

    from duckclaw.spawn_profile import effective_hub_read_only

    assert effective_hub_read_only(str(hub), True) is True
