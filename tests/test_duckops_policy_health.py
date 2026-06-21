from __future__ import annotations


def test_format_chat_status_bar_includes_model_worker_tokens() -> None:
    from duckops.sovereign.tui_chat_status import format_chat_status_bar

    bar = format_chat_status_bar(
        worker_id="default",
        tenant_id="acme",
        llm_label="deepseek · deepseek-chat",
        usage={"total_tokens": 2400},
    )
    assert "deepseek" in bar
    assert "default" in bar
    assert "2.4K tok" in bar


def test_check_framework_policies_ok_after_migrate() -> None:
    import duckdb

    from duckclaw.schema_migrations import run_pending_migrations
    from duckops.policy_health import check_framework_prompt_policies

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    health = check_framework_prompt_policies(con)
    assert health.ok is True
    assert not health.missing_keys


def test_check_framework_policies_degraded_without_db_rows() -> None:
    import duckdb

    from duckclaw.schema_migrations import run_pending_migrations
    from duckops.policy_health import check_framework_prompt_policies

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    con.execute("DELETE FROM main.prompt_policy_registry WHERE policy_type = 'capability'")
    health = check_framework_prompt_policies(con)
    assert health.ok is True
    assert health.degraded is True
    assert "capability/generic_worker" in health.degraded_keys


def test_catalog_prompt_check_skips_dormant_imported_workers() -> None:
    import duckdb

    from duckclaw.schema_migrations import run_pending_migrations
    from duckops.policy_health import check_catalog_worker_system_prompts

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    con.execute(
        """
        INSERT INTO main.admin_worker_catalog
          (worker_uid, tenant_id, owner_email, worker_id, display_name, source_kind, active)
        VALUES
          ('uid_aws', 'default', 'admin@test', 'aws-expert-agent', 'AWS Expert', 'template', true)
        """
    )
    health = check_catalog_worker_system_prompts(con)
    assert health.ok is True
    assert "aws-expert-agent" not in health.missing_worker_ids


def test_catalog_prompt_check_flags_runtime_workers_without_policy() -> None:
    import duckdb

    from duckclaw.schema_migrations import run_pending_migrations
    from duckops.policy_health import check_catalog_worker_system_prompts

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    con.execute(
        """
        INSERT INTO main.admin_worker_catalog
          (worker_uid, tenant_id, owner_email, worker_id, display_name, source_kind, active)
        VALUES
          ('uid_mine', 'default', 'admin@test', 'my-agent', 'Mi agente', 'runtime', true)
        """
    )
    health = check_catalog_worker_system_prompts(con)
    assert health.ok is False
    assert "my-agent" in health.missing_worker_ids
