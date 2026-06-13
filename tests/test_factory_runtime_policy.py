from __future__ import annotations

from types import SimpleNamespace


def _runtime_policy(*, name: str, policy: dict | None = None):
    from duckclaw.workers.identity import WorkerCapability, WorkerRuntimePolicy

    capability = WorkerCapability(
        capability_id=f"cap_{name}",
        name=name,
        kind="runtime_policy",
        provider="duckclaw",
        permission="use",
        config={},
        policy=policy or {},
        quota={},
    )
    return WorkerRuntimePolicy(
        worker_id="worker_alpha",
        identity=None,
        capabilities=(capability,),
    )


def test_factory_runtime_capability_helper_reads_worker_policy() -> None:
    from duckclaw.workers.factory import _worker_has_runtime_capability

    spec = SimpleNamespace(runtime_policy=_runtime_policy(name="field_reflection"))

    assert _worker_has_runtime_capability(spec, "field_reflection")
    assert not _worker_has_runtime_capability(spec, "bounded_json_read")
    assert not _worker_has_runtime_capability(SimpleNamespace(runtime_policy=None), "field_reflection")


def test_factory_runtime_capability_flag_coerces_policy_values() -> None:
    from duckclaw.workers.factory import _worker_runtime_capability_flag

    spec = SimpleNamespace(
        runtime_policy=_runtime_policy(
            name="portfolio_live_bridge",
            policy={"enabled_by_default": "true", "disabled_by_default": "off"},
        )
    )

    assert _worker_runtime_capability_flag(
        spec,
        "portfolio_live_bridge",
        "enabled_by_default",
        default=False,
    )
    assert not _worker_runtime_capability_flag(
        spec,
        "portfolio_live_bridge",
        "disabled_by_default",
        default=True,
    )
    assert _worker_runtime_capability_flag(
        spec,
        "bounded_json_read",
        "enabled_by_default",
        default=True,
    )
