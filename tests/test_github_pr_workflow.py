"""Tests flujo GitHub PR determinista (owner, rama, manifest)."""

from __future__ import annotations

import pytest


def test_github_infer_branch_from_incoming_fix_branch() -> None:
    from duckclaw.workers.factory import _github_infer_branch_from_incoming

    text = "Create branch fix/quant-hallucination-loop, commit changes, open PR"
    assert _github_infer_branch_from_incoming(text) == "fix/quant-hallucination-loop"


def test_github_push_manifest_skips_hallucination_fix() -> None:
    from duckclaw.workers.factory import _github_push_manifest_for_intent

    incoming = "Fix quant hallucination loop and open PR fix/quant-hallucination-loop"
    assert _github_push_manifest_for_intent(incoming, "fix/quant-hallucination-loop") is None


def test_github_push_manifest_for_cancel_trade_signal() -> None:
    from duckclaw.workers.factory import _github_push_manifest_for_intent

    incoming = "Complete cancel_trade_signal PR on feat/cancel-trade-signal-tool"
    manifest = _github_push_manifest_for_intent(incoming, "feat/cancel-trade-signal-tool")
    assert manifest is not None
    assert "trade_signal_cancel.py" in manifest[0]


def test_github_resolve_owner_repo_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.workers import factory as f

    monkeypatch.setenv("GITHUB_OWNER", "TestOrg")
    monkeypatch.setenv("GITHUB_REPO", "TestRepo")
    owner, repo = f._github_resolve_owner_repo()
    assert owner == "TestOrg"
    assert repo == "TestRepo"


def test_github_pr_workflow_guardrail_exists() -> None:
    from duckclaw.guardrails.loader import load_guardrail

    body = load_guardrail("directives", "github_pr_workflow")
    assert "push_files" in body
    assert "create_pull_request" in body
