"""Smoke: ADF validator sobre forge/templates/<agente> AXIS (6 agentes)."""

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

_ADF_PATH = REPO_ROOT / "packages" / "agents" / "src" / "duckclaw" / "adf_validator.py"
_spec = importlib.util.spec_from_file_location("adf_validator", _ADF_PATH)
assert _spec and _spec.loader
_adf = importlib.util.module_from_spec(_spec)
sys.modules["adf_validator"] = _adf
_spec.loader.exec_module(_adf)
REQUIRED_FILES = _adf.REQUIRED_FILES
AXIS_ADF_AGENT_IDS = _adf.AXIS_ADF_AGENT_IDS
validate_agent = _adf.validate_agent
validate_all_agents = _adf.validate_all_agents


def test_validate_all_agents_ok() -> None:
    results = validate_all_agents(REPO_ROOT)
    assert results, "debe existir validación para los 6 agentes AXIS"
    assert set(results.keys()) == set(AXIS_ADF_AGENT_IDS)
    for agent, result in results.items():
        assert result.valid, f"{agent}: {result.errors}"


@pytest.mark.parametrize(
    "agent_id",
    ["coder", "mirror", "radar", "sentinel", "phantom", "maestro"],
)
def test_each_axis_agent_has_seven_files(agent_id: str) -> None:
    adf = (
        REPO_ROOT
        / "packages"
        / "agents"
        / "src"
        / "duckclaw"
        / "forge"
        / "templates"
        / agent_id
    )
    assert adf.is_dir()
    for name in REQUIRED_FILES:
        assert (adf / name).is_file(), f"{agent_id}: falta {name}"


def test_validate_agent_slug_matches_manifest() -> None:
    coder_adf = (
        REPO_ROOT
        / "packages"
        / "agents"
        / "src"
        / "duckclaw"
        / "forge"
        / "templates"
        / "coder"
    )
    r = validate_agent(coder_adf)
    assert r.valid
    assert r.agent_id == "coder"
