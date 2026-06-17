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
