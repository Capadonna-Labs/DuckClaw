"""Guardrails for removed FMP vertical tools."""

from __future__ import annotations

import importlib


def test_fmp_bridge_is_not_core_skill() -> None:
    try:
        importlib.import_module("duckclaw.forge.skills.fmp_bridge")
    except ModuleNotFoundError:
        return

    raise AssertionError("FMP bridge must live outside core or behind DB-first extension registration")


def test_fmp_symbols_not_exported_from_core_skills_package() -> None:
    skills = importlib.import_module("duckclaw.forge.skills")

    assert not hasattr(skills, "fmp_bridge")
