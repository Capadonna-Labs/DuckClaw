from __future__ import annotations

import json
from types import SimpleNamespace

import pytest


def test_classify_risk_tiers() -> None:
    from duckclaw.workers.tool_harness import classify_tool_risk

    assert classify_tool_risk("read_sql") == "read"
    assert classify_tool_risk("list_tool_packs") == "read"
    assert classify_tool_risk("patch_report_section") == "write"
    assert classify_tool_risk("mcp__github__list_issues") == "network"
    assert classify_tool_risk("mcp__github__push_files") == "destructive"
    assert classify_tool_risk("delete_output_document") == "destructive"
    assert classify_tool_risk("run_sandbox") == "destructive"


def test_approval_blocks_only_destructive() -> None:
    from duckclaw.workers.tool_harness import approval_blocks_execution

    assert approval_blocks_execution("read", "suggest") is False
    assert approval_blocks_execution("network", "suggest") is False
    assert approval_blocks_execution("destructive", "auto") is False
    assert approval_blocks_execution("destructive", "suggest") is True
    assert approval_blocks_execution("destructive", "never") is True


def test_circuit_breaker_counts() -> None:
    from duckclaw.workers.tool_harness import (
        circuit_should_block,
        record_tool_failure,
    )

    counts: dict[str, int] = {}
    counts = record_tool_failure(counts, "mcp__github__x")
    assert circuit_should_block(counts, "mcp__github__x", 2) is False
    counts = record_tool_failure(counts, "mcp__github__x")
    assert circuit_should_block(counts, "mcp__github__x", 2) is True


def test_normalize_plain_error_to_envelope() -> None:
    from duckclaw.workers.tool_harness import content_indicates_failure, normalize_tool_failure

    out = normalize_tool_failure("Error: boom")
    payload = json.loads(out)
    assert payload["ok"] is False
    assert payload["retry"] is True
    assert content_indicates_failure(out) is True


def test_truncate_tool_result() -> None:
    from duckclaw.workers.tool_harness import truncate_tool_result

    text, truncated = truncate_tool_result("a" * 100, 50)
    assert truncated is True
    assert len(text) < 100
    assert "truncated" in text


def test_resolve_harness_from_spec() -> None:
    from duckclaw.workers.tool_harness import resolve_harness_config

    spec = SimpleNamespace(
        tool_surface_config={
            "harness": {
                "approval_mode": "never",
                "max_failures_per_tool": 3,
                "max_tool_result_chars": 2000,
            }
        }
    )
    cfg = resolve_harness_config(spec)
    assert cfg["approval_mode"] == "never"
    assert cfg["max_failures_per_tool"] == 3
    assert cfg["max_tool_result_chars"] == 2000
