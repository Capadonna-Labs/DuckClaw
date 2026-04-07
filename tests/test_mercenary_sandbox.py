"""Tests Caged Beast / mercenario (parse, política Manager, Docker opcional)."""

from __future__ import annotations

from pathlib import Path

import pytest

from duckclaw.forge.schema import SecurityPolicy, load_security_policy


def test_load_security_policy_manager_template() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    worker_dir = (
        repo_root
        / "packages"
        / "agents"
        / "src"
        / "duckclaw"
        / "forge"
        / "templates"
        / "Manager"
    )
    policy = load_security_policy("Manager", worker_dir=worker_dir)
    assert isinstance(policy, SecurityPolicy)
    assert policy.network.default == "deny"
    assert policy.max_execution_time_seconds <= 600


def test_run_mercenary_ephemeral_async_no_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.graphs import sandbox as sb

    monkeypatch.setattr(sb, "_docker_available", lambda: False)
    import asyncio

    out = asyncio.run(sb.run_mercenary_ephemeral_async("hello", 30, task_id="t1"))
    assert out.get("ok") is False
    assert out.get("error_code") == "MERCENARY_DOCKER_UNAVAILABLE"


def test_run_mercenary_ephemeral_empty_directive() -> None:
    import asyncio

    from duckclaw.graphs import sandbox as sb

    out = asyncio.run(sb.run_mercenary_ephemeral_async("  ", 30, task_id="t2"))
    assert out.get("ok") is False
    assert out.get("error_code") == "MERCENARY_INVALID_INPUT"


@pytest.mark.skipif(
    not __import__("duckclaw.graphs.sandbox", fromlist=["_docker_available"])._docker_available(),
    reason="Docker daemon no disponible",
)
def test_run_mercenary_ephemeral_smoke_integration() -> None:
    """Un contenedor efímero; omitir en CI sin Docker."""
    from duckclaw.graphs.sandbox import run_mercenary_ephemeral

    out = run_mercenary_ephemeral("smoke probe", 60, task_id="pytest_merc")
    assert out.get("ok") is True
    assert (out.get("result") or {}).get("status") == "stub_completed"
    assert "directive_digest" in (out.get("result") or {})
