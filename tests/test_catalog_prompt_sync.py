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


def test_sync_all_catalog_worker_prompts_backfills_active_workers(gateway_db) -> None:
    import duckdb

    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.admin_worker_catalog import add_worker_version, create_worker
    from duckclaw.catalog_prompt_sync import sync_all_catalog_worker_prompts
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(str(gateway_db))
    try:
        run_pending_migrations(con)
        ensure_profile_for_user(con, email="admin@test.local")
        worker_a = create_worker(
            con,
            owner_email="admin@test.local",
            worker_id="sync-alpha",
            display_name="Sync Alpha",
            source_kind="template_import",
        )
        worker_b = create_worker(
            con,
            owner_email="admin@test.local",
            worker_id="sync-beta",
            display_name="Sync Beta",
            source_kind="template_import",
        )
        add_worker_version(
            con,
            worker_uid=worker_a["worker_uid"],
            created_by="admin@test.local",
            files_snapshot={"system_prompt.md": "# Alpha prompt"},
        )
        add_worker_version(
            con,
            worker_uid=worker_b["worker_uid"],
            created_by="admin@test.local",
            files_snapshot={"soul.md": "Beta soul"},
        )
        result = sync_all_catalog_worker_prompts(
            con,
            actor_email="admin@test.local",
        )
        alpha_row = con.execute(
            """
            SELECT content FROM main.prompt_policy_registry
            WHERE policy_type = 'system_prompt' AND policy_name = 'sync-alpha'
            ORDER BY version DESC LIMIT 1
            """
        ).fetchone()
        beta_row = con.execute(
            """
            SELECT content FROM main.prompt_policy_registry
            WHERE policy_type = 'system_prompt' AND policy_name = 'sync-beta'
            ORDER BY version DESC LIMIT 1
            """
        ).fetchone()
    finally:
        con.close()

    assert result["synced"] == ["sync-alpha", "sync-beta"]
    assert result["failed"] == []
    assert alpha_row is not None
    assert "Alpha prompt" in str(alpha_row[0])
    assert beta_row is not None
    assert "Beta soul" in str(beta_row[0])


def test_sync_all_catalog_worker_prompts_skips_without_prompt_files(gateway_db) -> None:
    import duckdb

    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.admin_worker_catalog import add_worker_version, create_worker
    from duckclaw.catalog_prompt_sync import sync_all_catalog_worker_prompts
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(str(gateway_db))
    try:
        run_pending_migrations(con)
        ensure_profile_for_user(con, email="admin@test.local")
        worker = create_worker(
            con,
            owner_email="admin@test.local",
            worker_id="sync-empty",
            display_name="Sync Empty",
            source_kind="template_import",
        )
        add_worker_version(
            con,
            worker_uid=worker["worker_uid"],
            created_by="admin@test.local",
            files_snapshot={"manifest.json": "{}"},
        )
        result = sync_all_catalog_worker_prompts(
            con,
            actor_email="admin@test.local",
        )
    finally:
        con.close()

    assert result["synced"] == []
    assert "sync-empty" in result["skipped"]
    assert result["failed"] == []


def test_sync_all_catalog_worker_prompts_idempotent_without_force(gateway_db) -> None:
    import duckdb

    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.admin_worker_catalog import add_worker_version, create_worker
    from duckclaw.catalog_prompt_sync import sync_all_catalog_worker_prompts
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(str(gateway_db))
    try:
        run_pending_migrations(con)
        ensure_profile_for_user(con, email="admin@test.local")
        worker = create_worker(
            con,
            owner_email="admin@test.local",
            worker_id="sync-idem",
            display_name="Sync Idem",
            source_kind="template_import",
        )
        add_worker_version(
            con,
            worker_uid=worker["worker_uid"],
            created_by="admin@test.local",
            files_snapshot={"system_prompt.md": "Same prompt"},
        )
        first = sync_all_catalog_worker_prompts(con, actor_email="admin@test.local")
        second = sync_all_catalog_worker_prompts(con, actor_email="admin@test.local")
        version_count = con.execute(
            """
            SELECT COUNT(*) FROM main.prompt_policy_registry
            WHERE policy_type = 'system_prompt' AND policy_name = 'sync-idem'
            """
        ).fetchone()[0]
    finally:
        con.close()

    assert first["synced"] == ["sync-idem"]
    assert second["skipped"] == ["sync-idem"]
    assert version_count == 1


def test_sync_catalog_prompts_command_handler(gateway_db) -> None:
    import duckdb

    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.admin_worker_catalog import add_worker_version, create_worker
    from duckclaw.schema_migrations import run_pending_migrations
    from duckclaw.write_command_handlers import dispatch_command

    con = duckdb.connect(str(gateway_db))
    try:
        run_pending_migrations(con)
        ensure_profile_for_user(con, email="admin@test.local")
        worker = create_worker(
            con,
            owner_email="admin@test.local",
            worker_id="sync-cmd",
            display_name="Sync Cmd",
            source_kind="template_import",
        )
        add_worker_version(
            con,
            worker_uid=worker["worker_uid"],
            created_by="admin@test.local",
            files_snapshot={"system_prompt.md": "Command prompt"},
        )
        payload = {
            "command_type": "sync_catalog_prompts",
            "actor_email": "admin@test.local",
            "force": False,
        }
        dispatch_command(con, payload)
        row = con.execute(
            """
            SELECT content FROM main.prompt_policy_registry
            WHERE policy_type = 'system_prompt' AND policy_name = 'sync-cmd'
            ORDER BY version DESC LIMIT 1
            """
        ).fetchone()
    finally:
        con.close()

    assert payload["_sync_result"]["synced"] == ["sync-cmd"]
    assert row is not None
    assert "Command prompt" in str(row[0])
