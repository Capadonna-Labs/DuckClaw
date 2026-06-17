from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _seed_policy(
    con,
    policy_type: str,
    policy_name: str,
    content: str,
    *,
    version: int = 1,
    status: str = "active",
    active: bool = True,
) -> None:
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    con.execute(
        """
        INSERT INTO main.prompt_policy_registry
          (policy_id, policy_type, policy_name, version, status, content, checksum, active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            f"{policy_type}_{policy_name}_{version}",
            policy_type,
            policy_name,
            version,
            status,
            content,
            checksum,
            active,
        ],
    )


def test_prompt_policy_resolver_loads_directives_from_db_only() -> None:
    import duckdb

    from duckclaw.prompt_policies import PromptPolicyResolver
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    _seed_policy(con, "directive", "tool_choice_generic", "elige una tool desde DB")

    resolver = PromptPolicyResolver(db=con)

    assert resolver.load("directives", "tool_choice_generic") == "elige una tool desde DB"


def test_prompt_policy_resolver_formats_capabilities_from_db_only() -> None:
    import duckdb

    from duckclaw.prompt_policies import PromptPolicyResolver
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)

    resolver = PromptPolicyResolver(db=con)

    formatted = resolver.format("capabilities", "generic_worker", worker_id="ciberseguridad-agent")
    assert "ciberseguridad-agent" in formatted


def test_prompt_policy_resolver_requires_db() -> None:
    import pytest

    from duckclaw.prompt_policies import PromptPolicyResolver

    with pytest.raises(RuntimeError, match="requires a DuckDB connection"):
        PromptPolicyResolver().load("directive", "tool_choice_generic")


def test_prompt_policy_resolver_fails_when_active_policy_missing() -> None:
    import duckdb
    import pytest

    from duckclaw.prompt_policies import PromptPolicyResolver
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    _seed_policy(
        con,
        "directive",
        "tool_choice_generic",
        "inactive content",
        status="inactive",
        active=False,
    )

    with pytest.raises(FileNotFoundError, match="active prompt policy not found"):
        PromptPolicyResolver(db=con).load("directive", "tool_choice_generic")


def test_prompt_policy_health_reports_missing_active_requirements() -> None:
    import duckdb

    from duckclaw.prompt_policies.health import (
        PromptPolicyRequirement,
        missing_prompt_policies,
    )
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    _seed_policy(con, "system_prompt", "present_worker", "contenido activo")
    _seed_policy(
        con,
        "capability",
        "inactive_capability",
        "contenido inactivo",
        status="inactive",
        active=False,
    )

    missing = missing_prompt_policies(
        con,
        [
            PromptPolicyRequirement("system_prompts", "present_worker", "catalog"),
            PromptPolicyRequirement("capabilities", "inactive_capability", "manager"),
            PromptPolicyRequirement("capability", "generic_worker", "manager"),
        ],
    )

    assert missing == [
        PromptPolicyRequirement("capability", "inactive_capability", "manager"),
    ]


def test_prompt_policy_registry_tables_exist() -> None:
    import duckdb

    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    tables = {
        row[0]
        for row in con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall()
    }

    assert "prompt_policy_registry" in tables
    assert "worker_prompt_bindings" in tables
    assert "tool_policy_directives" in tables


def test_framework_capability_policies_are_seeded_by_migrations() -> None:
    import duckdb

    from duckclaw.prompt_policies import PromptPolicyResolver
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)

    resolver = PromptPolicyResolver(db=con)
    assert "{worker_id}" in resolver.load("capability", "generic_worker")
    assert "{coord}" in resolver.load("capability", "axis_coordinator")
    assert resolver.load("capability", "default_fallback")
    assert "DuckDB" in resolver.load("system_prompt", "default")


def test_managed_workspace_draft_policy_is_seeded_by_migrations() -> None:
    import duckdb

    from duckclaw.prompt_policies import PromptPolicyResolver
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)

    content = PromptPolicyResolver(db=con).load("manager_task", "admin_workspace_managed_draft")
    policy = json.loads(content)

    assert policy["draft_prompt_template"]
    assert policy["fallback"]["worker_id_template"]
    assert policy["confirm"]["source_kind"]
    assert "Platform Orchestrator" not in content
    assert "platform-orchestrator" not in content


def test_directives_and_capabilities_markdown_dirs_are_removed() -> None:
    root = Path("packages/agents/src/duckclaw/guardrails")

    assert not (root / "directives").exists()
    assert not (root / "capabilities").exists()
