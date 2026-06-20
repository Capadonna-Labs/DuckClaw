"""Tests for framework_tool_pack v1 baseline merge."""

from __future__ import annotations

import os

import pytest

from duckclaw.framework_tool_pack import (
    baseline_skills_for_profile,
    ensure_baseline_skill_configs,
    ensure_baseline_skills,
    ensure_baseline_worker_files,
    load_framework_tool_pack,
    should_apply_framework_baseline,
)


def test_load_framework_tool_pack_has_baseline() -> None:
    pack = load_framework_tool_pack()
    assert pack["pack_version"] == "framework_tool_pack_v1"
    baseline = pack["baseline_skills"]
    assert "read_sql" in baseline
    assert "search_project_knowledge" in baseline
    assert "write_output_document" in baseline


def test_ensure_baseline_skills_merges_without_duplicates() -> None:
    merged = ensure_baseline_skills(["read_sql", "fal"], manifest={"tool_profile": "general"})
    assert merged[0] == "read_sql"
    assert "fal" in merged
    assert "list_project_knowledge" in merged
    assert len(merged) == len(set(merged))


def test_ensure_baseline_skills_respects_opt_out() -> None:
    raw = ["read_sql"]
    assert ensure_baseline_skills(raw, manifest={"baseline": False}) == ["read_sql"]


def test_internal_scaffold_skips_baseline() -> None:
    assert should_apply_framework_baseline({"internal_scaffold": True}) is False
    merged = ensure_baseline_skills([], manifest={"internal_scaffold": True})
    assert merged == []


def test_minimal_profile() -> None:
    minimal = baseline_skills_for_profile("minimal")
    assert minimal == ["get_current_time", "read_sql"]
    merged = ensure_baseline_skills([], manifest={"tool_profile": "minimal"})
    assert merged == minimal


def test_optional_research_when_tavily_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    skills = ensure_baseline_skills([], manifest={"tool_profile": "general"})
    assert "research" in skills
    configs = ensure_baseline_skill_configs({}, skills=skills, manifest={"tool_profile": "general"})
    assert configs["research"]["tavily_enabled"] is True


def test_optional_research_without_key() -> None:
    os.environ.pop("TAVILY_API_KEY", None)
    skills = ensure_baseline_skills([], manifest={"tool_profile": "general"})
    assert "research" not in skills


def test_ensure_baseline_worker_files_writes_policy(tmp_path) -> None:
    worker_dir = tmp_path / "agent-a"
    worker_dir.mkdir()
    ensure_baseline_worker_files(worker_dir)
    policy = worker_dir / "security_policy.yaml"
    assert policy.is_file()
    text = policy.read_text(encoding="utf-8")
    assert "network:" in text
    assert "max_execution_time_seconds" in text
