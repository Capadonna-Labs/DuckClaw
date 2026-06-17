from __future__ import annotations

import importlib
import inspect
from typing import Any

from duckclaw.graphs import on_the_fly_commands


CANONICAL_MODULE = "duckclaw.commands.goals"
GOALS_EXPORTS = (
    "_normalize_belief_key",
    "_get_goals_registry_fallback_first",
    "_get_goals_registry_for_chat",
    "list_goal_signal_autocomplete",
    "get_manager_goals",
    "set_manager_goals",
    "_goal_title",
    "_natural_language_goal_to_params",
    "_persist_homeostasis_manifest_db",
    "_format_homeostasis_manifest_listing",
    "execute_homeostasis_goals",
)


def test_goals_command_ownership_lives_outside_graphs() -> None:
    goals = importlib.import_module(CANONICAL_MODULE)

    for name in GOALS_EXPORTS:
        exported = getattr(on_the_fly_commands, name)
        assert exported.__module__ == CANONICAL_MODULE

    source = inspect.getsource(goals)
    assert "duckclaw.graphs.on_the_fly_commands" not in source
    assert "from duckclaw.graphs" not in source


def test_goals_registry_does_not_fallback_to_filesystem_manifests() -> None:
    goals = importlib.import_module(CANONICAL_MODULE)
    source = inspect.getsource(goals)

    forbidden = {
        "duckclaw.workers.manifest",
        "duckclaw.workers.factory",
        "load_manifest",
        "list_workers",
        "templates/workers",
        "homeostasis_config",
        "forge_context",
    }
    leaked = sorted(marker for marker in forbidden if marker in source)

    assert leaked == []
    assert "duckclaw.worker_quality_signals" in source


def test_goals_autocomplete_reads_quality_signals_without_manifests(monkeypatch: Any) -> None:
    from duckclaw.commands import goals as goals_module

    calls: list[tuple[str, str]] = []

    def _fake_options(db: Any, *, tenant_id: str, worker_id: str) -> list[Any]:
        del db
        calls.append((tenant_id, worker_id))
        from duckclaw.worker_quality_signals import WorkerQualitySignalOption

        return [
            WorkerQualitySignalOption(
                key="latency_ms",
                label="Latencia",
                target=250.0,
                threshold=25.0,
                comparison="ceiling",
            )
        ]

    monkeypatch.setattr(
        "duckclaw.worker_quality_signals.list_worker_quality_signal_options",
        _fake_options,
    )

    out = goals_module.list_goal_signal_autocomplete(
        object(),
        tenant_id="tenant_a",
        worker_id="analytics-worker",
    )

    assert calls == [("tenant_a", "analytics-worker")]
    assert out == [
        {
            "key": "latency_ms",
            "label": "Latencia",
            "target": 250.0,
            "threshold": 25.0,
            "comparison": "ceiling",
        }
    ]


def test_on_the_fly_goals_imports_remain_compatible() -> None:
    goals = importlib.import_module(CANONICAL_MODULE)

    for name in GOALS_EXPORTS:
        assert getattr(on_the_fly_commands, name) is getattr(goals, name)
