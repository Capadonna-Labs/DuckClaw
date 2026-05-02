"""Unit tests GitHub MCP bridge (Docker argv / env merge, allowlist lectura)."""

from __future__ import annotations

import os

import pytest


def test_github_docker_run_argv_read_write_excludes_read_only_pass_through() -> None:
    from duckclaw.forge.skills.github_bridge import github_docker_run_argv

    argv = github_docker_run_argv(read_only=False)
    assert argv[0] == "run"
    assert "--pull=missing" in argv
    assert "GITHUB_READ_ONLY" not in argv
    assert argv[-1].endswith("github-mcp-server") or "/" in argv[-1]


def test_github_docker_run_argv_read_only_adds_pass_through_env() -> None:
    from duckclaw.forge.skills.github_bridge import github_docker_run_argv

    argv = github_docker_run_argv(read_only=True)
    assert "GITHUB_READ_ONLY" in argv
    assert argv[-1] == "ghcr.io/github/github-mcp-server" or argv[-1].endswith("github-mcp-server")


def test_github_mcp_merged_child_env_read_only_flag() -> None:
    from duckclaw.forge.skills.github_bridge import github_mcp_merged_child_env

    m = github_mcp_merged_child_env("dummy-token", read_only=True, toolsets="repos")
    assert m["GITHUB_READ_ONLY"] == "1"
    assert m["GITHUB_TOOLSETS"] == "repos"
    assert m["GITHUB_PERSONAL_ACCESS_TOKEN"] == "dummy-token"


def test_github_worker_allows_gitclaw_not_random() -> None:
    from duckclaw.forge.skills.github_bridge import github_worker_allows_mutating_mcp

    assert github_worker_allows_mutating_mcp("gitclaw") is True
    assert github_worker_allows_mutating_mcp("finanz") is False


def test_github_worker_env_csv_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.forge.skills.github_bridge import github_worker_allows_mutating_mcp

    monkeypatch.setenv("DUCKCLAW_GITHUB_MCP_READWRITE_WORKERS", "foo, GITCLAW ,bar")
    assert github_worker_allows_mutating_mcp("foo") is True
    assert github_worker_allows_mutating_mcp("bar") is True
