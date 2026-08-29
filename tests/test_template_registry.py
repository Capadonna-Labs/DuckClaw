"""Resolución de alias de plantillas forge (agent_id → carpeta)."""

from __future__ import annotations

from duckclaw.workers.template_registry import resolve_template_id, resolve_template_id_global


def test_maestro_alias_resolves_to_axis_maestro() -> None:
    all_ids = ["default", "default", "platform-orchestrator"]
    assert resolve_template_id(all_ids, "default") == "default"
    assert resolve_template_id_global("default") == "default"


def test_folder_name_case_insensitive() -> None:
    all_ids = ["default"]
    assert resolve_template_id(all_ids, "default") == "default"


def test_hyphen_underscore_alias_resolves_against_available() -> None:
    available = ["default", "quant-trader", "quant_reporter"]
    assert resolve_template_id(available, "quant_trader") == "quant-trader"
    assert resolve_template_id(available, "quant-trader") == "quant-trader"
    assert resolve_template_id(available, "quant_reporter") == "quant_reporter"
    assert resolve_template_id(available, "quant-reporter") == "quant_reporter"
