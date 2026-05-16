"""Resolución de alias de plantillas forge (agent_id → carpeta)."""

from __future__ import annotations

from duckclaw.workers.template_registry import resolve_template_id, resolve_template_id_global


def test_maestro_alias_resolves_to_axis_maestro() -> None:
    all_ids = ["AXIS-Maestro", "AXIS-Coder", "finanz"]
    assert resolve_template_id(all_ids, "maestro") == "AXIS-Maestro"
    assert resolve_template_id_global("maestro") == "AXIS-Maestro"


def test_folder_name_case_insensitive() -> None:
    all_ids = ["AXIS-Radar"]
    assert resolve_template_id(all_ids, "axis-radar") == "AXIS-Radar"
