from __future__ import annotations

from pathlib import Path

import duckdb
import pytest


class _Adapter:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def execute(self, sql: str, params=None):
        if params is not None:
            return self._con.execute(sql, params)
        return self._con.execute(sql)


def _columns(con: duckdb.DuckDBPyConnection, table_name: str) -> set[str]:
    return {
        str(row[1])
        for row in con.execute(f"PRAGMA table_info('main.{table_name}')").fetchall()
    }


def test_worker_catalog_keeps_identity_separate_from_import_snapshots(gateway_db: Path) -> None:
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.admin_worker_catalog import (
        add_worker_version,
        create_worker,
        ensure_admin_worker_catalog_schema,
    )

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        profile = ensure_profile_for_user(adapter, email="alice@test.local")
        ensure_admin_worker_catalog_schema(adapter)

        worker = create_worker(
            adapter,
            owner_email="alice@test.local",
            worker_id="axis-coder",
            display_name="AXIS Coder",
            source_template_id="default",
        )
        version = add_worker_version(
            adapter,
            worker_uid=worker["worker_uid"],
            created_by="alice@test.local",
            manifest_snapshot={"id": "axis-coder", "name": "AXIS Coder"},
            files_snapshot={"system_prompt.md": "# Contexto"},
            change_note="Import inicial",
        )

        catalog_columns = _columns(con, "admin_worker_catalog")
        version_columns = _columns(con, "admin_worker_versions")
    finally:
        con.close()

    assert worker["tenant_id"] == profile["tenant_id"]
    assert worker["worker_id"] == "axis-coder"
    assert version["version"] == 1
    assert "manifest_json" not in catalog_columns
    assert "files_json" not in catalog_columns
    assert {"manifest_snapshot_json", "files_snapshot_json"}.issubset(version_columns)


def test_worker_catalog_enforces_tenant_scoped_unique_worker_ids(gateway_db: Path) -> None:
    from duckclaw.admin_worker_catalog import create_worker

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        create_worker(
            adapter,
            owner_email="alice@test.local",
            worker_id="axis-coder",
            display_name="AXIS Coder",
        )
        create_worker(
            adapter,
            owner_email="bob@test.local",
            worker_id="axis-coder",
            display_name="Bob AXIS Coder",
        )
        with pytest.raises(ValueError, match="worker_id ya existe"):
            create_worker(
                adapter,
                owner_email="alice@test.local",
                worker_id="axis-coder",
                display_name="Duplicate",
            )
    finally:
        con.close()


def test_contexts_skills_and_capabilities_are_many_to_many(gateway_db: Path) -> None:
    from duckclaw.admin_worker_catalog import (
        add_worker_context,
        attach_skill_to_worker,
        create_worker,
        grant_worker_capability,
        list_worker_capabilities,
        list_worker_contexts,
        list_worker_skills,
        register_capability,
        register_skill,
    )

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        coder = create_worker(
            adapter,
            owner_email="alice@test.local",
            worker_id="axis-coder",
            display_name="AXIS Coder",
        )
        mirror = create_worker(
            adapter,
            owner_email="alice@test.local",
            worker_id="axis-mirror",
            display_name="AXIS Mirror",
        )
        add_worker_context(adapter, worker_uid=coder["worker_uid"], title="Dominio", content_md="# Dominio", sort_order=20)
        add_worker_context(adapter, worker_uid=coder["worker_uid"], title="Estilo", content_md="# Estilo", sort_order=10)

        skill = register_skill(adapter, name="crm_lookup", skill_type="python", implementation_ref="duckclaw.skills.crm")
        attach_skill_to_worker(adapter, worker_uid=coder["worker_uid"], skill_id=skill["skill_id"])
        attach_skill_to_worker(adapter, worker_uid=mirror["worker_uid"], skill_id=skill["skill_id"])

        capability = register_capability(
            adapter,
            name="duckdb_read",
            kind="duckdb",
            provider="duckclaw",
            risk_level="medium",
            requires_secret=False,
            requires_network=False,
        )
        grant_worker_capability(
            adapter,
            worker_uid=coder["worker_uid"],
            capability_id=capability["capability_id"],
            permission="read",
        )

        contexts = list_worker_contexts(adapter, worker_uid=coder["worker_uid"])
        coder_skills = list_worker_skills(adapter, worker_uid=coder["worker_uid"])
        mirror_skills = list_worker_skills(adapter, worker_uid=mirror["worker_uid"])
        capabilities = list_worker_capabilities(adapter, worker_uid=coder["worker_uid"])
    finally:
        con.close()

    assert [c["title"] for c in contexts] == ["Estilo", "Dominio"]
    assert [s["name"] for s in coder_skills] == ["crm_lookup"]
    assert [s["name"] for s in mirror_skills] == ["crm_lookup"]
    assert capabilities[0]["name"] == "duckdb_read"
    assert capabilities[0]["permission"] == "read"


def test_projects_attach_agents_and_list_only_actor_workspace(gateway_db: Path) -> None:
    from duckclaw.admin_worker_catalog import create_worker
    from duckclaw.admin_workspace import (
        attach_agent_to_project,
        create_project,
        list_project_agents,
        list_projects_for_actor,
    )

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        alice_worker = create_worker(
            adapter,
            owner_email="alice@test.local",
            worker_id="axis-coder",
            display_name="AXIS Coder",
        )
        alice_project = create_project(
            adapter,
            owner_email="alice@test.local",
            name="AXIS Platform",
            description="Trabajo privado de Alice",
        )
        bob_project = create_project(
            adapter,
            owner_email="bob@test.local",
            name="Bob Workspace",
            description="Trabajo privado de Bob",
        )
        attach_agent_to_project(
            adapter,
            project_id=alice_project["project_id"],
            worker_uid=alice_worker["worker_uid"],
            role="coder",
        )

        alice_projects = list_projects_for_actor(adapter, actor_email="alice@test.local")
        bob_projects = list_projects_for_actor(adapter, actor_email="bob@test.local")
        alice_agents = list_project_agents(adapter, project_id=alice_project["project_id"], actor_email="alice@test.local")
    finally:
        con.close()

    assert {p["project_id"] for p in alice_projects} == {alice_project["project_id"]}
    assert {p["project_id"] for p in bob_projects} == {bob_project["project_id"]}
    assert alice_agents[0]["worker_uid"] == alice_worker["worker_uid"]
    assert alice_agents[0]["role"] == "coder"


def test_resource_events_record_cross_cutting_audit_without_owning_permissions(gateway_db: Path) -> None:
    from duckclaw.admin_resources import (
        list_resource_events,
        record_resource_event,
    )
    from duckclaw.admin_workspace import create_project

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        project = create_project(
            adapter,
            owner_email="alice@test.local",
            name="AXIS Platform",
            description="Auditado",
        )
        record_resource_event(
            adapter,
            tenant_id=project["tenant_id"],
            actor_email="alice@test.local",
            resource_kind="project",
            resource_id=project["project_id"],
            event_type="project.created",
            payload={"name": "AXIS Platform", "secret": "redacted"},
        )
        events = list_resource_events(adapter, tenant_id=project["tenant_id"])
    finally:
        con.close()

    assert events[0]["resource_kind"] == "project"
    assert events[0]["resource_id"] == project["project_id"]
    assert events[0]["event_type"] == "project.created"
    assert "secret" not in events[0]["payload_redacted_json"]


def test_workspace_catalog_migration_and_bootstrap_are_idempotent(gateway_db: Path) -> None:
    import importlib

    from duckclaw.bootstrap_core import bootstrap_core_schema

    migration = importlib.import_module("scripts.migrations.004_admin_workspace_catalog")
    expected_tables = {
        "admin_worker_catalog",
        "admin_worker_versions",
        "admin_worker_assignments",
        "admin_worker_contexts",
        "admin_skills",
        "admin_worker_skills",
        "admin_capabilities",
        "admin_worker_capabilities",
        "admin_projects",
        "admin_project_members",
        "admin_project_agents",
        "admin_resource_events",
        "admin_resource_tags",
        "admin_secret_refs",
    }

    con = duckdb.connect(str(gateway_db))
    try:
        migration.apply_migration(con)
        migration.apply_migration(con)
        bootstrap_core_schema(_Adapter(con), seed_admin=False)
        tables = {
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
        }
    finally:
        con.close()

    assert expected_tables.issubset(tables)


def test_gateway_templates_lists_default_and_actor_catalog_not_all_filesystem_templates(
    gateway_admin_client,
) -> None:
    from duckclaw import DuckClaw
    from duckclaw.admin_worker_catalog import create_worker
    from duckclaw.gateway_db import get_gateway_db_path

    db = DuckClaw(get_gateway_db_path(), read_only=False, engine="python")
    try:
        create_worker(
            db,
            owner_email="admin@test.local",
            worker_id="axis-coder",
            display_name="AXIS Coder",
        )
    finally:
        db.close()

    response = gateway_admin_client.get(
        "/api/v1/admin/templates",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
    )

    assert response.status_code == 200
    templates = {item["id"]: item for item in response.json()["templates"]}
    assert "default" in templates
    assert templates["axis-coder"]["name"] == "AXIS Coder"
    assert "AXIS-Mirror" not in templates


def test_gateway_template_detail_rejects_unassigned_filesystem_template(
    gateway_admin_client,
) -> None:
    response = gateway_admin_client.get(
        "/api/v1/admin/templates/AXIS-Mirror",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
    )

    assert response.status_code == 404


def test_playground_config_uses_db_first_visible_workers_not_all_filesystem_templates(
    gateway_admin_client,
) -> None:
    from duckclaw import DuckClaw
    from duckclaw.admin_worker_catalog import create_worker
    from duckclaw.gateway_db import get_gateway_db_path

    db = DuckClaw(get_gateway_db_path(), read_only=False, engine="python")
    try:
        create_worker(
            db,
            owner_email="admin@test.local",
            worker_id="axis-coder",
            display_name="AXIS Coder",
        )
    finally:
        db.close()

    response = gateway_admin_client.get(
        "/api/v1/admin/playground/config",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
    )

    assert response.status_code == 200
    workers = {item["id"]: item for item in response.json()["workers"]}
    assert "default" in workers
    assert workers["axis-coder"]["label"] == "AXIS Coder"
    assert "AXIS-Mirror" not in workers


def test_playground_chat_rejects_unassigned_filesystem_worker_before_execution(
    gateway_admin_client,
) -> None:
    response = gateway_admin_client.post(
        "/api/v1/admin/playground/chat",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
        json={"worker_id": "AXIS-Mirror", "message": "hola"},
    )

    assert response.status_code == 403
