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

    formatted = resolver.format(
        "capabilities",
        "generic_worker",
        worker_id="ciberseguridad-agent",
        tenant_id="default",
    )
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


def test_classify_prompt_policy_health_marks_catalog_worker_without_row_as_inherited() -> None:
    import duckdb

    from duckclaw.admin_worker_catalog import create_worker
    from duckclaw.prompt_policies.health import (
        INHERITED_SYSTEM_PROMPT_WARNING,
        PromptPolicyRequirement,
        classify_prompt_policy_health,
    )
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    create_worker(
        con,
        owner_email="ops@duckclaw.local",
        worker_id="axis-maestro",
        display_name="Axis Maestro",
    )

    classification = classify_prompt_policy_health(
        con,
        [
            PromptPolicyRequirement("system_prompt", "axis-maestro", "worker"),
            PromptPolicyRequirement("system_prompt", "ghost-worker", "worker"),
        ],
    )

    assert classification.ok == ()
    assert classification.missing == (
        PromptPolicyRequirement("system_prompt", "ghost-worker", "worker"),
    )
    assert classification.inherited == (
        PromptPolicyRequirement("system_prompt", "axis-maestro", "worker"),
    )
    assert classification.is_ok is False
    assert INHERITED_SYSTEM_PROMPT_WARNING == "especialización pendiente"


def test_classify_prompt_policy_health_keeps_framework_missing_critical() -> None:
    import duckdb

    from duckclaw.prompt_policies.health import (
        PromptPolicyRequirement,
        classify_prompt_policy_health,
    )
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    con.execute(
        """
        UPDATE main.prompt_policy_registry
        SET active = false, status = 'inactive'
        WHERE policy_type = 'capability' AND policy_name = 'generic_worker'
        """
    )

    classification = classify_prompt_policy_health(
        con,
        [PromptPolicyRequirement("capability", "generic_worker", "framework")],
    )

    assert classification.ok == ()
    assert classification.inherited == ()
    assert classification.missing == (
        PromptPolicyRequirement("capability", "generic_worker", "framework"),
    )


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
    default_prompt = resolver.load("system_prompt", "default")
    assert "## IDENTITY" in default_prompt
    assert "DuckClaw" in default_prompt
    assert "{tenant_id}" in default_prompt


def test_framework_fallback_used_when_db_row_missing() -> None:
    import duckdb

    from duckclaw.prompt_policies import PromptPolicyResolver
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    con.execute(
        """
        UPDATE main.prompt_policy_registry
        SET active = false, status = 'inactive'
        WHERE policy_type = 'capability' AND policy_name = 'generic_worker'
        """
    )

    content = PromptPolicyResolver(db=con).load("capability", "generic_worker")
    assert "{worker_id}" in content
    assert "DuckClaw" in content


def test_system_prompt_worker_inherits_default_when_missing() -> None:
    import duckdb

    from duckclaw.prompt_policies import PromptPolicyResolver
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)

    inherited = PromptPolicyResolver(db=con).load("system_prompt", "axis-maestro")
    default = PromptPolicyResolver(db=con).load("system_prompt", "default")
    assert inherited == default


def test_framework_pack_keys_match_requirements() -> None:
    from duckclaw.prompt_policies.framework_fallbacks import list_framework_fallback_keys
    from duckclaw.prompt_policies.health import FRAMEWORK_PROMPT_POLICY_REQUIREMENTS

    required = {
        (policy_type, policy_name)
        for policy_type, policy_name, _source in FRAMEWORK_PROMPT_POLICY_REQUIREMENTS
    }
    assert list_framework_fallback_keys() == frozenset(required)


def test_migration_021_upgrades_framework_pack_content() -> None:
    import duckdb

    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)

    row = con.execute(
        """
        SELECT content, metadata_json, version
        FROM main.prompt_policy_registry
        WHERE policy_type = 'system_prompt'
          AND policy_name = 'default'
          AND active = true
        ORDER BY version DESC
        LIMIT 1
        """
    ).fetchone()
    assert row is not None
    content = row[0]
    metadata = row[1]
    version = row[2]
    assert version >= 2
    assert "## IDENTITY" in content
    assert "framework_policy_pack_v1" in metadata


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
