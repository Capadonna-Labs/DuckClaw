from __future__ import annotations

from duckclaw.write_task_detail import format_write_task_success_detail


def test_sync_catalog_detail() -> None:
    detail = format_write_task_success_detail(
        "sync_catalog_prompts",
        {"_sync_result": {"synced": ["a", "b"], "skipped": ["c"], "failed": []}},
    )
    assert detail == "synced=2, skipped=1, failed=0"


def test_restore_framework_detail() -> None:
    detail = format_write_task_success_detail(
        "restore_framework_policy_pack",
        {"_applied": ["p1", "p2", "p3"]},
    )
    assert detail == "applied=3"


def test_unknown_command_returns_none() -> None:
    assert format_write_task_success_detail("upsert_prompt_policy", {}) is None
