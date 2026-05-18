"""Política efectiva de red sandbox por chat."""

from __future__ import annotations

import pytest

from duckclaw.forge.schema import resolve_sandbox_network_policy


def test_resolve_yaml_deny_ignores_chat_true(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.forge.schema import SecurityPolicy

    base = SecurityPolicy()
    base.network.default = "deny"

    monkeypatch.setattr(
        "duckclaw.forge.schema.load_security_policy",
        lambda _wid, worker_dir=None: base,
    )
    eff, meta = resolve_sandbox_network_policy("Quant-Trader", "true")
    assert meta["yaml_default"] == "deny"
    assert meta["effective"] == "deny"
    assert meta["toggle_available"] is False
    assert eff.network.default == "deny"


def test_resolve_yaml_allow_chat_false_forces_deny(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.forge.schema import SecurityPolicy

    base = SecurityPolicy()
    base.network.default = "allow"

    monkeypatch.setattr(
        "duckclaw.forge.schema.load_security_policy",
        lambda _wid, worker_dir=None: base,
    )
    eff, meta = resolve_sandbox_network_policy("finanz", "false")
    assert meta["toggle_available"] is True
    assert meta["effective"] == "deny"
    assert eff.network.default == "deny"


def test_resolve_yaml_allow_chat_true_keeps_allow(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.forge.schema import SecurityPolicy

    base = SecurityPolicy()
    base.network.default = "allow"

    monkeypatch.setattr(
        "duckclaw.forge.schema.load_security_policy",
        lambda _wid, worker_dir=None: base,
    )
    eff, meta = resolve_sandbox_network_policy("finanz", "true")
    assert meta["effective"] == "allow"
    assert eff.network.default == "allow"


def test_resolve_yaml_allow_empty_uses_yaml(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.forge.schema import SecurityPolicy

    base = SecurityPolicy()
    base.network.default = "allow"

    monkeypatch.setattr(
        "duckclaw.forge.schema.load_security_policy",
        lambda _wid, worker_dir=None: base,
    )
    eff, meta = resolve_sandbox_network_policy("finanz", None)
    assert meta["effective"] == "allow"
    assert eff.network.default == "allow"
