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


def test_resolve_security_policy_for_chat_uses_runtime_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    import duckclaw
    from duckclaw.admin_runtime_settings import upsert_runtime_setting
    from duckclaw.forge.schema import SecurityPolicy, resolve_security_policy_for_chat

    base = SecurityPolicy()
    base.network.default = "allow"
    db = duckclaw.DuckClaw(":memory:")
    upsert_runtime_setting(
        db,
        tenant_id="default",
        actor_email="chat:chat-a",
        domain="runtime.session",
        key="sandbox_network_enabled",
        value_text="false",
    )

    monkeypatch.setattr(
        "duckclaw.forge.schema.load_security_policy",
        lambda _wid, worker_dir=None: base,
    )
    monkeypatch.setattr(
        "duckclaw.graphs.on_the_fly_commands.get_chat_state",
        lambda *_args, **_kwargs: "true",
    )

    eff, meta = resolve_security_policy_for_chat("default", db, "chat-a")

    assert meta["effective"] == "deny"
    assert meta["chat_override"] == "false"
    assert eff.network.default == "deny"


def test_resolve_security_policy_for_chat_uses_explicit_tenant_scope(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import duckclaw
    from duckclaw.admin_runtime_settings import upsert_runtime_setting
    from duckclaw.forge.schema import SecurityPolicy, resolve_security_policy_for_chat

    base = SecurityPolicy()
    base.network.default = "allow"
    db = duckclaw.DuckClaw(":memory:")
    upsert_runtime_setting(
        db,
        tenant_id="tenant-a",
        actor_email="chat:chat-a",
        domain="runtime.session",
        key="sandbox_network_enabled",
        value_text="false",
    )

    monkeypatch.setattr(
        "duckclaw.forge.schema.load_security_policy",
        lambda _wid, worker_dir=None: base,
    )

    _, default_meta = resolve_security_policy_for_chat("default", db, "chat-a")
    eff, tenant_meta = resolve_security_policy_for_chat(
        "default",
        db,
        "chat-a",
        tenant_id="tenant-a",
    )

    assert default_meta["effective"] == "allow"
    assert tenant_meta["effective"] == "deny"
    assert eff.network.default == "deny"
