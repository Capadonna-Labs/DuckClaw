from __future__ import annotations


def test_build_system_prompt_content_from_files_merges_soul_and_system() -> None:
    from duckclaw.catalog_prompt_sync import build_system_prompt_content_from_files

    content = build_system_prompt_content_from_files(
        {
            "soul.md": "SOUL",
            "system_prompt.md": "SYS",
        }
    )
    assert content == "SOUL\n\n---\n\nSYS"


def test_sync_requires_catalog_row(gateway_db) -> None:
    import duckdb

    from duckclaw.catalog_prompt_sync import sync_worker_system_prompt_policy
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(str(gateway_db))
    try:
        run_pending_migrations(con)
        written = sync_worker_system_prompt_policy(
            con,
            worker_id="ghost-worker",
            files={"system_prompt.md": "nope"},
            actor_email="admin@test.local",
        )
    finally:
        con.close()

    assert written is False


def test_sync_worker_system_prompt_policy_writes_registry(gateway_db) -> None:
    import duckdb

    from duckclaw.admin_worker_catalog import create_worker
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.catalog_prompt_sync import sync_worker_system_prompt_policy
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(str(gateway_db))
    try:
        run_pending_migrations(con)
        ensure_profile_for_user(con, email="admin@test.local")
        worker = create_worker(
            con,
            owner_email="admin@test.local",
            worker_id="axis-maestro",
            display_name="Axis Maestro",
            source_kind="template_import",
            source_template_id="default",
        )
        written = sync_worker_system_prompt_policy(
            con,
            worker_id="axis-maestro",
            files={"system_prompt.md": "# Worker prompt\nHola."},
            actor_email="admin@test.local",
            worker_uid=str(worker.get("worker_uid") or ""),
        )
        row = con.execute(
            """
            SELECT content, active
            FROM main.prompt_policy_registry
            WHERE policy_type = 'system_prompt' AND policy_name = 'axis-maestro'
            ORDER BY version DESC
            LIMIT 1
            """
        ).fetchone()
    finally:
        con.close()

    assert written is True
    assert row is not None
    assert "Worker prompt" in str(row[0])
    assert row[1] is True
