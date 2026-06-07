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


def test_platform_orchestrator_is_seeded_per_actor_and_versioned(gateway_db: Path) -> None:
    from duckclaw.admin_worker_catalog import (
        ensure_platform_orchestrator_for_actor,
        get_latest_worker_version,
    )

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        alice = ensure_platform_orchestrator_for_actor(adapter, actor_email="alice@test.local")
        alice_again = ensure_platform_orchestrator_for_actor(adapter, actor_email="alice@test.local")
        bob = ensure_platform_orchestrator_for_actor(adapter, actor_email="bob@test.local")
        latest = get_latest_worker_version(adapter, worker_uid=alice["worker_uid"])
    finally:
        con.close()

    assert alice["worker_id"] == "platform-orchestrator"
    assert alice["display_name"] == "Platform Orchestrator"
    assert alice["source_kind"] == "system_seed"
    assert alice["visibility"] == "private"
    assert alice["worker_uid"] == alice_again["worker_uid"]
    assert bob["worker_uid"] != alice["worker_uid"]
    assert latest is not None
    assert latest["manifest_snapshot"]["id"] == "platform-orchestrator"
    assert "system_prompt.md" in latest["files_snapshot"]


def test_gateway_templates_auto_seed_platform_orchestrator(gateway_admin_client) -> None:
    response = gateway_admin_client.get(
        "/api/v1/admin/templates",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "alice@test.local"},
    )

    assert response.status_code == 200
    templates = {item["id"]: item for item in response.json()["templates"]}
    assert templates["platform-orchestrator"]["source"] == "catalog"
    assert templates["platform-orchestrator"]["visibility"] == "private"
    assert templates["platform-orchestrator"]["active"] is True


def test_orchestrator_draft_suggests_available_skills_without_creating_project(
    gateway_db: Path,
    gateway_admin_client,
) -> None:
    from duckclaw.admin_worker_catalog import register_skill

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        register_skill(
            adapter,
            name="crm_lookup",
            description="Consulta clientes CRM",
            skill_type="python",
            implementation_ref="duckclaw.skills.crm",
            owner_email="alice@test.local",
        )
        before_projects = con.execute(
            "SELECT COUNT(*) FROM main.admin_projects"
        ).fetchone()[0]
    finally:
        con.close()

    response = gateway_admin_client.post(
        "/api/v1/admin/workspace/orchestrator/draft",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "alice@test.local"},
        json={"prompt": "Crear un proyecto para consultar clientes CRM y responder casos de soporte"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["project"]["name"]
    assert body["workers"][0]["worker_id"]
    assert any(skill["name"] == "crm_lookup" and skill["available"] for skill in body["suggested_skills"])

    con = duckdb.connect(str(gateway_db))
    try:
        after_projects = con.execute("SELECT COUNT(*) FROM main.admin_projects").fetchone()[0]
    finally:
        con.close()
    assert after_projects == before_projects


def test_orchestrator_confirm_creates_project_workers_context_and_assignments(
    gateway_db: Path,
    gateway_admin_client,
) -> None:
    draft = {
        "project": {"name": "Soporte CRM", "description": "Atiende casos con datos CRM"},
        "workers": [
            {
                "worker_id": "crm-support-agent",
                "display_name": "CRM Support Agent",
                "role": "member",
                "system_prompt": "Ayuda a resolver casos usando contexto CRM.",
            }
        ],
        "shared_context": "# Contexto CRM\nUsar tono claro.",
        "suggested_skills": [{"name": "crm_lookup", "reason": "consulta clientes", "available": False}],
        "questions": [],
    }
    response = gateway_admin_client.post(
        "/api/v1/admin/workspace/orchestrator/confirm",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "alice@test.local"},
        json={"draft": draft},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["project"]["name"] == "Soporte CRM"
    assert payload["created"]["workers"][0]["worker_id"] == "crm-support-agent"

    con = duckdb.connect(str(gateway_db))
    try:
        row = con.execute(
            """
            SELECT p.name, wc.worker_id, ctx.title
            FROM main.admin_projects p
            JOIN main.admin_project_agents pa ON pa.project_id = p.project_id
            JOIN main.admin_worker_catalog wc ON wc.worker_uid = pa.worker_uid
            JOIN main.admin_worker_contexts ctx ON ctx.worker_uid = wc.worker_uid
            WHERE p.project_id = ?
            """,
            [payload["project"]["project_id"]],
        ).fetchone()
    finally:
        con.close()

    assert row == ("Soporte CRM", "crm-support-agent", "Contexto compartido")


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


def test_gateway_workspace_projects_assign_and_remove_catalog_workers(
    gateway_admin_client,
    gateway_db: Path,
) -> None:
    from duckclaw import DuckClaw
    from duckclaw.admin_worker_catalog import create_worker

    headers = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"}
    db = DuckClaw(str(gateway_db), read_only=False, engine="python")
    try:
        create_worker(
            db,
            owner_email="admin@test.local",
            worker_id="axis-radar",
            display_name="AXIS Radar",
        )
    finally:
        db.close()

    created = gateway_admin_client.post(
        "/api/v1/admin/workspace/projects",
        headers=headers,
        json={"name": "Operación AXIS", "description": "Proyecto DB-first"},
    )
    assert created.status_code == 200
    project = created.json()["project"]
    project_id = project["project_id"]

    assigned = gateway_admin_client.post(
        f"/api/v1/admin/workspace/projects/{project_id}/agents",
        headers=headers,
        json={"worker_id": "axis-radar", "role": "coordinator", "sort_order": 10},
    )
    assert assigned.status_code == 200
    assert assigned.json()["agent"]["worker_id"] == "axis-radar"
    assert assigned.json()["agent"]["role"] == "coordinator"

    listed = gateway_admin_client.get(
        f"/api/v1/admin/workspace/projects/{project_id}/agents",
        headers=headers,
    )
    assert listed.status_code == 200
    assert [agent["worker_id"] for agent in listed.json()["agents"]] == ["axis-radar"]

    projects = gateway_admin_client.get("/api/v1/admin/workspace/projects", headers=headers)
    assert projects.status_code == 200
    visible = {item["project_id"]: item for item in projects.json()["projects"]}
    assert visible[project_id]["agent_count"] == 1

    removed = gateway_admin_client.delete(
        f"/api/v1/admin/workspace/projects/{project_id}/agents/axis-radar",
        headers=headers,
    )
    assert removed.status_code == 200

    listed_after = gateway_admin_client.get(
        f"/api/v1/admin/workspace/projects/{project_id}/agents",
        headers=headers,
    )
    assert listed_after.json()["agents"] == []

    deleted = gateway_admin_client.delete(
        f"/api/v1/admin/workspace/projects/{project_id}",
        headers=headers,
    )
    assert deleted.status_code == 200
    assert deleted.json() == {"ok": True, "project_id": project_id}

    projects_after = gateway_admin_client.get("/api/v1/admin/workspace/projects", headers=headers)
    assert projects_after.status_code == 200
    assert project_id not in {item["project_id"] for item in projects_after.json()["projects"]}

    con = duckdb.connect(str(gateway_db), read_only=True)
    try:
        project_row = con.execute(
            "SELECT active, status FROM main.admin_projects WHERE project_id = ?",
            [project_id],
        ).fetchone()
        worker_count = con.execute(
            "SELECT COUNT(*) FROM main.admin_worker_catalog WHERE worker_id = 'axis-radar'",
        ).fetchone()[0]
    finally:
        con.close()

    assert project_row == (False, "inactive")
    assert worker_count == 1


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
    assert templates["axis-coder"]["worker_uid"]
    assert templates["axis-coder"]["visibility"] == "private"
    assert templates["axis-coder"]["source_template_id"] == "default"
    assert "AXIS-Mirror" not in templates


def test_gateway_templates_can_list_and_reactivate_inactive_catalog_worker(
    gateway_admin_client,
    gateway_db: Path,
) -> None:
    from duckclaw import DuckClaw
    from duckclaw.admin_worker_catalog import create_worker, deactivate_visible_worker_for_actor
    from duckclaw.gateway_db import get_gateway_db_path

    headers = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"}
    db = DuckClaw(get_gateway_db_path(), read_only=False, engine="python")
    try:
        create_worker(
            db,
            owner_email="admin@test.local",
            worker_id="ejemplo",
            display_name="Ejemplo",
        )
        deactivate_visible_worker_for_actor(db, actor_email="admin@test.local", worker_id="ejemplo")
    finally:
        db.close()

    active_only = gateway_admin_client.get("/api/v1/admin/templates", headers=headers)
    assert active_only.status_code == 200
    assert "ejemplo" not in {item["id"] for item in active_only.json()["templates"]}

    with_inactive = gateway_admin_client.get(
        "/api/v1/admin/templates?include_inactive=true",
        headers=headers,
    )
    assert with_inactive.status_code == 200
    templates = {item["id"]: item for item in with_inactive.json()["templates"]}
    assert templates["ejemplo"]["active"] is False
    assert templates["ejemplo"]["status"] == "inactive"

    reactivated = gateway_admin_client.post(
        "/api/v1/admin/templates/ejemplo/reactivate",
        headers=headers,
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["action"] == "reactivated"

    listed_after = gateway_admin_client.get("/api/v1/admin/templates", headers=headers)
    assert "ejemplo" in {item["id"] for item in listed_after.json()["templates"]}


def test_get_visible_worker_for_actor_accepts_boolean_active_rows(gateway_db: Path) -> None:
    from duckclaw import DuckClaw
    from duckclaw.admin_worker_catalog import create_worker, get_visible_worker_for_actor

    db = DuckClaw(str(gateway_db), read_only=False, engine="python")
    try:
        create_worker(
            db,
            owner_email="admin@test.local",
            worker_id="axis-maestro",
            display_name="AXIS Maestro",
        )
        worker = get_visible_worker_for_actor(
            db,
            actor_email="admin@test.local",
            worker_id="axis-maestro",
        )
    finally:
        db.close()

    assert worker is not None
    assert worker["worker_id"] == "axis-maestro"


def test_gateway_rejects_default_template_deactivation_explicitly(gateway_admin_client) -> None:
    response = gateway_admin_client.delete(
        "/api/v1/admin/templates/default",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["title"] == "Plantilla protegida"


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


def test_playground_config_for_console_actor_does_not_mix_legacy_team_ids_with_catalog(
    gateway_admin_client,
) -> None:
    from duckclaw import DuckClaw
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.admin_worker_catalog import create_worker
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.graphs.on_the_fly_commands import set_tenant_team_templates

    db = DuckClaw(get_gateway_db_path(), read_only=False, engine="python")
    try:
        profile = ensure_profile_for_user(db, email="admin@test.local")
        set_tenant_team_templates(db, profile["tenant_id"], ["AXIS-Maestro", "AXIS-Radar"])
        create_worker(
            db,
            owner_email="admin@test.local",
            worker_id="axis-maestro",
            display_name="MAESTRO",
        )
        create_worker(
            db,
            owner_email="admin@test.local",
            worker_id="axis-radar",
            display_name="RADAR",
        )
    finally:
        db.close()

    response = gateway_admin_client.get(
        "/api/v1/admin/playground/config",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
    )

    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["workers"]]
    assert "axis-maestro" in ids
    assert "axis-radar" in ids
    assert "AXIS-Maestro" not in ids
    assert "AXIS-Radar" not in ids
    assert len(ids) == len(set(ids))


def test_playground_chat_rejects_unassigned_filesystem_worker_before_execution(
    gateway_admin_client,
) -> None:
    response = gateway_admin_client.post(
        "/api/v1/admin/playground/chat",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
        json={"worker_id": "AXIS-Mirror", "message": "hola"},
    )

    assert response.status_code == 403


def test_playground_config_and_chat_support_db_first_project_scope(
    gateway_admin_client,
    gateway_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw import DuckClaw
    from duckclaw.admin_worker_catalog import create_worker
    from duckclaw.admin_workspace import attach_agent_to_project, create_project
    import main as gateway_main

    headers = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"}
    db = DuckClaw(str(gateway_db), read_only=False, engine="python")
    try:
        radar = create_worker(
            db,
            owner_email="admin@test.local",
            worker_id="axis-radar",
            display_name="AXIS Radar",
        )
        create_worker(
            db,
            owner_email="admin@test.local",
            worker_id="axis-sentinel",
            display_name="AXIS Sentinel",
        )
        project = create_project(
            db,
            owner_email="admin@test.local",
            name="Operación AXIS",
            description="Scope para Playground",
        )
        attach_agent_to_project(
            db,
            project_id=project["project_id"],
            worker_uid=radar["worker_uid"],
            role="coordinator",
        )
    finally:
        db.close()

    config = gateway_admin_client.get("/api/v1/admin/playground/config", headers=headers)
    assert config.status_code == 200
    projects = {item["project_id"]: item for item in config.json()["projects"]}
    assert projects[project["project_id"]]["name"] == "Operación AXIS"
    assert [agent["worker_id"] for agent in projects[project["project_id"]]["agents"]] == ["axis-radar"]

    async def _fake_invoke(_chat, worker_id, **_kwargs):
        return {"response": f"ok:{worker_id}", "assigned_worker_id": worker_id}

    monkeypatch.setattr(gateway_main, "_invoke_chat", _fake_invoke)

    chat = gateway_admin_client.post(
        "/api/v1/admin/playground/chat",
        headers=headers,
        json={
            "project_id": project["project_id"],
            "worker_id": "axis-radar",
            "message": "hola",
            "chat_id": "project-playground",
        },
    )
    assert chat.status_code == 200
    assert chat.json()["project_id"] == project["project_id"]
    assert chat.json()["worker_id"] == "axis-radar"

    rejected = gateway_admin_client.post(
        "/api/v1/admin/playground/chat",
        headers=headers,
        json={
            "project_id": project["project_id"],
            "worker_id": "axis-sentinel",
            "message": "hola",
            "chat_id": "project-playground",
        },
    )
    assert rejected.status_code == 403
