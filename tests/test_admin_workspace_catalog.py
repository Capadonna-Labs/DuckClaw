from __future__ import annotations

import hashlib
import json
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


def test_update_catalog_worker_file_syncs_manifest_snapshot_from_yaml(gateway_db: Path) -> None:
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.admin_worker_catalog import (
        add_worker_version,
        create_worker,
        ensure_admin_worker_catalog_schema,
        get_latest_worker_version,
        update_catalog_worker_file,
    )

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        ensure_profile_for_user(adapter, email="alice@test.local")
        ensure_admin_worker_catalog_schema(adapter)

        worker = create_worker(
            adapter,
            owner_email="alice@test.local",
            worker_id="skills-sync",
            display_name="Skills Sync",
        )
        add_worker_version(
            adapter,
            worker_uid=worker["worker_uid"],
            created_by="alice@test.local",
            manifest_snapshot={"id": "skills-sync", "skills": []},
            files_snapshot={"manifest.yaml": "id: skills-sync\nskills: []\n"},
        )

        manifest_yaml = (
            "id: skills-sync\n"
            "name: Skills Sync\n"
            "tool_profile: general\n"
            "skills:\n"
            "  - publish_custom_report\n"
            "  - google_trends\n"
        )
        update_catalog_worker_file(
            adapter,
            worker_uid=worker["worker_uid"],
            file_path="manifest.yaml",
            content=manifest_yaml,
            actor_email="alice@test.local",
        )
        latest = get_latest_worker_version(adapter, worker_uid=worker["worker_uid"]) or {}
        manifest = latest.get("manifest_snapshot") or {}
        files = latest.get("files_snapshot") or {}
    finally:
        con.close()

    assert manifest.get("id") == "skills-sync"
    assert "publish_custom_report" in (manifest.get("skills") or [])
    assert "google_trends" in (manifest.get("skills") or [])
    assert files.get("manifest.yaml") == manifest_yaml


def test_update_catalog_worker_file_syncs_admin_worker_skills_for_catalog_skills_only(
    gateway_db: Path,
) -> None:
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.admin_worker_catalog import (
        add_worker_version,
        create_worker,
        ensure_admin_worker_catalog_schema,
        list_worker_skills,
        register_skill,
        update_catalog_worker_file,
    )

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        ensure_profile_for_user(adapter, email="alice@test.local")
        ensure_admin_worker_catalog_schema(adapter)

        worker = create_worker(
            adapter,
            owner_email="alice@test.local",
            worker_id="skills-junction",
            display_name="Skills Junction",
        )
        add_worker_version(
            adapter,
            worker_uid=worker["worker_uid"],
            created_by="alice@test.local",
            manifest_snapshot={"id": "skills-junction", "skills": []},
            files_snapshot={"manifest.yaml": "id: skills-junction\nskills: []\n"},
        )
        skill = register_skill(
            adapter,
            name="ticket_lookup",
            skill_type="python",
            implementation_ref="duckclaw.skills.ticket_lookup",
            owner_email="alice@test.local",
            tenant_id=worker["tenant_id"],
        )

        manifest_with_catalog_skill = (
            "id: skills-junction\n"
            "skills:\n"
            "  - ticket_lookup\n"
            "  - google_trends\n"
        )
        result = update_catalog_worker_file(
            adapter,
            worker_uid=worker["worker_uid"],
            file_path="manifest.yaml",
            content=manifest_with_catalog_skill,
            actor_email="alice@test.local",
        )
        bound = list_worker_skills(adapter, worker_uid=worker["worker_uid"])

        manifest_without_catalog_skill = (
            "id: skills-junction\n"
            "skills:\n"
            "  - google_trends\n"
        )
        update_catalog_worker_file(
            adapter,
            worker_uid=worker["worker_uid"],
            file_path="manifest.yaml",
            content=manifest_without_catalog_skill,
            actor_email="alice@test.local",
        )
        bound_after = list_worker_skills(adapter, worker_uid=worker["worker_uid"])
    finally:
        con.close()

    assert result["catalog_skills_synced"]["attached"] == 1
    assert len(bound) == 1
    assert bound[0]["skill_id"] == skill["skill_id"]
    assert bound[0]["name"] == "ticket_lookup"
    assert len(bound_after) == 0


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


def test_worker_catalog_does_not_seed_non_default_platform_worker(gateway_db: Path) -> None:
    from duckclaw.admin_worker_catalog import list_visible_workers_for_actor

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        visible = list_visible_workers_for_actor(adapter, actor_email="alice@test.local")
        catalog_count = con.execute("SELECT COUNT(*) FROM main.admin_worker_catalog").fetchone()[0]
    finally:
        con.close()

    assert [worker["worker_id"] for worker in visible] == []
    assert catalog_count == 0


def test_gateway_templates_do_not_auto_seed_platform_worker(gateway_admin_client) -> None:
    response = gateway_admin_client.get(
        "/api/v1/admin/templates",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "alice@test.local"},
    )

    assert response.status_code == 200, response.text
    templates = {item["id"]: item for item in response.json()["templates"]}
    assert "default" not in templates
    assert "platform" + "-orchestrator" not in templates


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
            name="ticket_lookup",
            description="Consulta tickets de soporte",
            skill_type="python",
            implementation_ref="duckclaw.skills.ticket_lookup",
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
        json={"prompt": "Crear un proyecto para consultar tickets y responder casos de soporte"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["project"]["name"]
    assert body["project"]["description"] != "Crear un proyecto para consultar tickets y responder casos de soporte"
    assert "Proyecto orientado" in body["project"]["description"]
    assert body["workers"][0]["worker_id"]
    assert body["workers"][0]["display_name"] != body["project"]["name"]
    assert "Asistente" in body["workers"][0]["display_name"]
    assert "Lectura del objetivo" in body["shared_context"]
    assert "Análisis del proyecto" in body["shared_context"]
    assert any(skill["name"] == "ticket_lookup" and skill["available"] for skill in body["suggested_skills"])

    con = duckdb.connect(str(gateway_db))
    try:
        after_projects = con.execute("SELECT COUNT(*) FROM main.admin_projects").fetchone()[0]
    finally:
        con.close()
    assert after_projects == before_projects


def test_orchestrator_draft_uses_configured_model_when_available(
    gateway_db: Path,
    gateway_admin_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import main as gateway_main

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-test")
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.local/v1")
    captured: dict[str, str] = {}

    async def _fake_invoke(chat, worker_id, **kwargs):
        captured["worker_id"] = worker_id
        captured["message"] = chat.message
        captured["session_id"] = kwargs.get("session_id", "")
        return {
            "response": """
            {
              "project": {
                "name": "Proyecto Ejemplo",
                "description": "Proyecto orientado a aprender FastAPI con práctica guiada y validación DB-first."
              },
              "workers": [
                {
                  "worker_id": "academia-fastapi-agent",
                  "display_name": "Asistente Ejemplo",
                  "role": "member",
                  "system_prompt": "Guía al usuario con ejercicios FastAPI y revisión paso a paso."
                }
              ],
              "shared_context": "Análisis del proyecto\\n\\nLectura del objetivo\\nAprender FastAPI.",
              "suggested_skills": [
                {"name": "fastapi_testing", "reason": "Pruebas de endpoints", "available": false}
              ],
              "questions": ["¿Qué nivel tienes en Python?"]
            }
            """,
            "assigned_worker_id": worker_id,
        }

    monkeypatch.setattr(gateway_main, "_invoke_chat", _fake_invoke)

    response = gateway_admin_client.post(
        "/api/v1/admin/workspace/orchestrator/draft",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "alice@test.local"},
        json={"prompt": "Quiero aprender FastAPI con ejercicios y guías"},
    )

    assert response.status_code == 200
    body = response.json()
    assert captured["worker_id"] == "default"
    assert "Responde SOLO JSON válido" in captured["message"]
    assert captured["session_id"].startswith("admin-managed-workspace-draft-")
    assert body["project"]["name"] == "Proyecto Ejemplo"
    assert body["workers"][0]["display_name"] == "Asistente Ejemplo"
    assert body["questions"] == ["¿Qué nivel tienes en Python?"]

    con = duckdb.connect(str(gateway_db))
    try:
        assert con.execute("SELECT COUNT(*) FROM main.admin_projects").fetchone()[0] == 0
    finally:
        con.close()


def test_orchestrator_draft_uses_db_first_prompt_policy_for_prompt_and_naming(
    gateway_db: Path,
    gateway_admin_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import main as gateway_main

    policy = {
        "draft_prompt_template": (
            "POLICY_JSON_ONLY skills={suggested_skills_json}\n"
            "POLICY_OBJECTIVE={prompt}"
        ),
        "fallback": {
            "project_name_template": "Policy Project {title}",
            "project_description_template": "Policy description for {goal}",
            "worker_id_template": "policy-{slug}-agent",
            "worker_display_name_template": "Policy Worker {project_name}",
            "worker_role": "member",
            "system_prompt_template": "Policy system prompt for {project_name}: {goal}",
            "shared_context_template": "Policy Context\n\nGoal: {prompt}",
            "model_error_note_template": "Policy model fallback note.",
            "questions": ["Policy question?"],
        },
        "confirm": {
            "source_kind": "managed_draft",
            "context_title": "Policy Context Title",
            "change_note": "Created from DB-first managed draft",
        },
    }
    content = json.dumps(policy, ensure_ascii=False)
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()

    con = duckdb.connect(str(gateway_db))
    try:
        con.execute(
            """
            INSERT INTO main.prompt_policy_registry
              (policy_id, policy_type, policy_name, version, status, content, checksum, active)
            VALUES (?, 'manager_task', 'admin_workspace_managed_draft', 2, 'active', ?, ?, true)
            """,
            ["test_admin_workspace_managed_draft_v2", content, checksum],
        )
    finally:
        con.close()

    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("LLM_MODEL", "gpt-test")
    monkeypatch.setenv("LLM_BASE_URL", "http://llm.local/v1")
    captured: dict[str, str] = {}

    async def _fake_invoke(chat, worker_id, **kwargs):
        captured["worker_id"] = worker_id
        captured["message"] = chat.message
        return {"response": "not json", "assigned_worker_id": worker_id}

    monkeypatch.setattr(gateway_main, "_invoke_chat", _fake_invoke)

    response = gateway_admin_client.post(
        "/api/v1/admin/workspace/orchestrator/draft",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "alice@test.local"},
        json={"prompt": "Crear una academia de FastAPI para el equipo interno"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert captured["worker_id"] == "default"
    assert "POLICY_JSON_ONLY" in captured["message"]
    assert "Platform Orchestrator" not in captured["message"]
    assert body["project"]["name"].startswith("Policy Project")
    assert body["workers"][0]["worker_id"].startswith("policy-")
    assert body["workers"][0]["display_name"].startswith("Policy Worker")
    assert body["workers"][0]["system_prompt"].startswith("Policy system prompt")
    assert body["shared_context"].startswith("Policy Context")
    assert body["questions"] == ["Policy question?"]


def test_orchestrator_draft_does_not_hardcode_fake_skill_suggestions(
    gateway_admin_client,
) -> None:
    response = gateway_admin_client.post(
        "/api/v1/admin/workspace/orchestrator/draft",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "alice@test.local"},
        json={"prompt": "Quiero aprender C++ moderno con ejercicios de consola"},
    )

    assert response.status_code == 200
    names = {skill["name"] for skill in response.json()["suggested_skills"]}
    assert "project_planning" not in names


def test_user_agent_draft_builds_structured_agent_without_persisting(
    gateway_db: Path,
    gateway_admin_client,
) -> None:
    con = duckdb.connect(str(gateway_db))
    try:
        before_agents = con.execute("SELECT COUNT(*) FROM main.admin_user_agents").fetchone()[0]
    finally:
        con.close()

    response = gateway_admin_client.post(
        "/api/v1/admin/user-agents/draft",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "alice@test.local"},
        json={
            "prompt": "Agente DevOps que revisa logs PM2, diagnostica el gateway y propone fixes en sandbox",
            "display_name": "Marco DevOps",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["display_name"]
    assert body["worker_id"]
    assert body["system_prompt"]
    assert "DevOps" in body["description"] or "devops" in body["description"].lower() or body["system_prompt"]
    assert body["tool_profile"] in {"general", "minimal", "rag_only"}
    assert isinstance(body["questions"], list)

    con = duckdb.connect(str(gateway_db))
    try:
        after_agents = con.execute("SELECT COUNT(*) FROM main.admin_user_agents").fetchone()[0]
    finally:
        con.close()
    assert after_agents == before_agents


def test_user_agent_draft_confirm_creates_runtime_agent(
    gateway_db: Path,
    gateway_admin_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("duckclaw.db_write_queue.spawn_inline_writes_enabled", lambda: True)
    draft_response = gateway_admin_client.post(
        "/api/v1/admin/user-agents/draft",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "alice@test.local"},
        json={"prompt": "Asistente que resume documentos técnicos y responde en español claro"},
    )
    assert draft_response.status_code == 200, draft_response.text
    draft = draft_response.json()
    draft["worker_id"] = "doc-summarizer-agent"

    confirm = gateway_admin_client.post(
        "/api/v1/admin/user-agents/draft/confirm",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "alice@test.local"},
        json={"draft": draft},
    )
    assert confirm.status_code == 200, confirm.text
    body = confirm.json()
    assert body["ok"] is True
    assert body["worker_id"] == "doc-summarizer-agent"

    con = duckdb.connect(str(gateway_db))
    try:
        row = con.execute(
            "SELECT worker_id, display_name FROM main.admin_user_agents WHERE worker_id = ?",
            ["doc-summarizer-agent"],
        ).fetchone()
    finally:
        con.close()
    assert row is not None


def test_orchestrator_confirm_creates_project_workers_context_and_assignments(
    gateway_db: Path,
    gateway_admin_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("duckclaw.db_write_queue.spawn_inline_writes_enabled", lambda: True)
    draft = {
        "project": {"name": "Soporte Tickets", "description": "Atiende casos con datos de soporte"},
        "workers": [
            {
                "worker_id": "ticket-support-agent",
                "display_name": "Ticket Support Agent",
                "role": "member",
                "system_prompt": "Ayuda a resolver casos usando contexto de soporte.",
            }
        ],
        "shared_context": "# Contexto soporte\nUsar tono claro.",
        "suggested_skills": [{"name": "ticket_lookup", "reason": "consulta tickets", "available": False}],
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
    assert payload["task_id"]
    assert payload["project"]["name"] == "Soporte Tickets"
    assert payload["created"]["workers"][0]["worker_id"] == "ticket-support-agent"

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

    assert row == ("Soporte Tickets", "ticket-support-agent", "Contexto compartido")


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

        skill = register_skill(
            adapter,
            name="ticket_lookup",
            skill_type="python",
            implementation_ref="duckclaw.skills.ticket_lookup",
        )
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
    assert [s["name"] for s in coder_skills] == ["ticket_lookup"]
    assert [s["name"] for s in mirror_skills] == ["ticket_lookup"]
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
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw import DuckClaw
    from duckclaw.admin_worker_catalog import create_worker

    monkeypatch.setattr("duckclaw.db_write_queue.spawn_inline_writes_enabled", lambda: True)
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
    assert created.json()["task_id"]
    project = created.json()["project"]
    project_id = project["project_id"]

    assigned = gateway_admin_client.post(
        f"/api/v1/admin/workspace/projects/{project_id}/agents",
        headers=headers,
        json={"worker_id": "axis-radar", "role": "coordinator", "sort_order": 10},
    )
    assert assigned.status_code == 200
    assert assigned.json()["task_id"]
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
    assert removed.json()["task_id"]

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
    assert deleted.json()["ok"] is True
    assert deleted.json()["hard_deleted"] is True
    assert deleted.json()["project_id"] == project_id
    assert deleted.json()["task_id"]

    projects_after = gateway_admin_client.get("/api/v1/admin/workspace/projects", headers=headers)
    assert projects_after.status_code == 200
    assert project_id not in {item["project_id"] for item in projects_after.json()["projects"]}

    con = duckdb.connect(str(gateway_db), read_only=True)
    try:
        project_count = con.execute(
            "SELECT COUNT(*) FROM main.admin_projects WHERE project_id = ?",
            [project_id],
        ).fetchone()
        agent_count = con.execute(
            "SELECT COUNT(*) FROM main.admin_project_agents WHERE project_id = ?",
            [project_id],
        ).fetchone()[0]
        member_count = con.execute(
            "SELECT COUNT(*) FROM main.admin_project_members WHERE project_id = ?",
            [project_id],
        ).fetchone()[0]
        worker_count = con.execute(
            "SELECT COUNT(*) FROM main.admin_worker_catalog WHERE worker_id = 'axis-radar'",
        ).fetchone()[0]
    finally:
        con.close()

    assert project_count == (0,)
    assert agent_count == 0
    assert member_count == 0
    assert worker_count == 1


def test_gateway_workspace_projects_support_search_sort_and_pagination(
    gateway_admin_client,
    gateway_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("duckclaw.db_write_queue.spawn_inline_writes_enabled", lambda: True)
    headers = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"}
    names = ["FastAPI Academy", "Ticket Support", "FastAPI RAG"]
    for name in names:
        created = gateway_admin_client.post(
            "/api/v1/admin/workspace/projects",
            headers=headers,
            json={"name": name, "description": f"Descripcion {name}"},
        )
        assert created.status_code == 200

    listed = gateway_admin_client.get(
        "/api/v1/admin/workspace/projects?q=fastapi&sort=name&direction=asc&limit=1&offset=0",
        headers=headers,
    )

    assert listed.status_code == 200
    payload = listed.json()
    assert payload["total"] == 2
    assert payload["limit"] == 1
    assert payload["offset"] == 0
    assert [project["name"] for project in payload["projects"]] == ["FastAPI Academy"]
    assert payload["projects"][0]["agents"] == []

    second_page = gateway_admin_client.get(
        "/api/v1/admin/workspace/projects?q=fastapi&sort=name&direction=asc&limit=1&offset=1",
        headers=headers,
    )

    assert second_page.status_code == 200
    assert second_page.json()["total"] == 2
    assert [project["name"] for project in second_page.json()["projects"]] == ["FastAPI RAG"]
    assert second_page.json()["projects"][0]["agents"] == []


def test_gateway_workspace_projects_can_deactivate_reactivate_and_hard_delete(
    gateway_admin_client,
    gateway_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("duckclaw.db_write_queue.spawn_inline_writes_enabled", lambda: True)
    headers = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"}
    created = gateway_admin_client.post(
        "/api/v1/admin/workspace/projects",
        headers=headers,
        json={"name": "Proyecto reversible", "description": "Debe poder pausarse"},
    )
    assert created.status_code == 200
    project_id = created.json()["project"]["project_id"]

    deactivated = gateway_admin_client.post(
        f"/api/v1/admin/workspace/projects/{project_id}/deactivate",
        headers=headers,
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["task_id"]
    assert deactivated.json()["project"]["status"] == "inactive"

    active_list = gateway_admin_client.get("/api/v1/admin/workspace/projects", headers=headers)
    assert project_id not in {item["project_id"] for item in active_list.json()["projects"]}

    inactive_list = gateway_admin_client.get(
        "/api/v1/admin/workspace/projects?status=inactive",
        headers=headers,
    )
    assert inactive_list.status_code == 200
    inactive = {item["project_id"]: item for item in inactive_list.json()["projects"]}
    assert inactive[project_id]["status"] == "inactive"

    playground = gateway_admin_client.get("/api/v1/admin/playground/config", headers=headers)
    assert project_id not in {item["project_id"] for item in playground.json()["projects"]}

    reactivated = gateway_admin_client.post(
        f"/api/v1/admin/workspace/projects/{project_id}/reactivate",
        headers=headers,
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["task_id"]
    assert reactivated.json()["project"]["status"] == "active"

    active_after = gateway_admin_client.get("/api/v1/admin/workspace/projects", headers=headers)
    assert project_id in {item["project_id"] for item in active_after.json()["projects"]}

    deactivated_again = gateway_admin_client.post(
        f"/api/v1/admin/workspace/projects/{project_id}/deactivate",
        headers=headers,
    )
    assert deactivated_again.status_code == 200
    assert deactivated_again.json()["task_id"]

    deleted = gateway_admin_client.delete(
        f"/api/v1/admin/workspace/projects/{project_id}",
        headers=headers,
    )
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True
    assert deleted.json()["hard_deleted"] is True
    assert deleted.json()["project_id"] == project_id
    assert deleted.json()["task_id"]

    con = duckdb.connect(str(gateway_db), read_only=True)
    try:
        project_count = con.execute(
            "SELECT COUNT(*) FROM main.admin_projects WHERE project_id = ?",
            [project_id],
        ).fetchone()[0]
    finally:
        con.close()
    assert project_count == 0


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


def test_gateway_templates_lists_actor_catalog_not_filesystem_templates(
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
    assert "default" not in templates
    assert templates["axis-coder"]["name"] == "AXIS Coder"
    assert templates["axis-coder"]["worker_uid"]
    assert templates["axis-coder"]["visibility"] == "private"
    assert templates["axis-coder"]["source_template_id"] == "default"
    assert "BI-Analyst" not in templates


def test_gateway_templates_can_list_and_reactivate_inactive_catalog_worker(
    gateway_admin_client,
    gateway_db: Path,
    monkeypatch: pytest.MonkeyPatch,
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
    monkeypatch.setattr("duckclaw.db_write_queue.spawn_inline_writes_enabled", lambda: True)

    reactivated = gateway_admin_client.post(
        "/api/v1/admin/templates/ejemplo/reactivate",
        headers=headers,
    )
    assert reactivated.status_code == 200
    assert reactivated.json()["action"] == "reactivated"

    listed_after = gateway_admin_client.get("/api/v1/admin/templates", headers=headers)
    assert "ejemplo" in {item["id"] for item in listed_after.json()["templates"]}


def test_gateway_templates_can_hard_delete_catalog_worker_relations(
    gateway_admin_client,
    gateway_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw import DuckClaw
    from duckclaw.admin_worker_catalog import (
        add_worker_context,
        add_worker_version,
        attach_skill_to_worker,
        create_worker,
        grant_worker_capability,
        register_capability,
        register_skill,
    )
    from duckclaw.admin_workspace import attach_agent_to_project, create_project
    from duckclaw.gateway_db import get_gateway_db_path

    headers = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"}
    db = DuckClaw(get_gateway_db_path(), read_only=False, engine="python")
    try:
        worker = create_worker(
            db,
            owner_email="admin@test.local",
            worker_id="delete-me",
            display_name="Delete Me",
        )
        add_worker_version(
            db,
            worker_uid=worker["worker_uid"],
            created_by="admin@test.local",
            manifest_snapshot={"id": "delete-me"},
            files_snapshot={"system_prompt.md": "hola"},
        )
        add_worker_context(
            db,
            worker_uid=worker["worker_uid"],
            title="Contexto",
            content_md="contexto",
        )
        skill = register_skill(
            db,
            name="delete_me_skill",
            description="Skill temporal",
            skill_type="atom",
            implementation_ref="tests.delete_me",
            owner_email="admin@test.local",
            tenant_id=worker["tenant_id"],
        )
        attach_skill_to_worker(db, worker_uid=worker["worker_uid"], skill_id=skill["skill_id"])
        capability = register_capability(
            db,
            name="delete_me_capability",
            kind="tool",
            provider="tests",
        )
        grant_worker_capability(
            db,
            worker_uid=worker["worker_uid"],
            capability_id=capability["capability_id"],
        )
        project = create_project(
            db,
            owner_email="admin@test.local",
            name="Proyecto con worker borrable",
        )
        attach_agent_to_project(
            db,
            project_id=project["project_id"],
            worker_uid=worker["worker_uid"],
        )
        worker_uid = worker["worker_uid"]
    finally:
        db.close()
    monkeypatch.setattr("duckclaw.db_write_queue.spawn_inline_writes_enabled", lambda: True)

    deleted = gateway_admin_client.delete(
        "/api/v1/admin/templates/delete-me/hard-delete",
        headers=headers,
    )
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True
    assert deleted.json()["id"] == "delete-me"
    assert deleted.json()["hard_deleted"] is True
    assert deleted.json()["task_id"]

    con = duckdb.connect(str(gateway_db), read_only=True)
    try:
        counts = {
            table: con.execute(
                f"SELECT COUNT(*) FROM main.{table} WHERE worker_uid = ?",
                [worker_uid],
            ).fetchone()[0]
            for table in [
                "admin_worker_catalog",
                "admin_worker_versions",
                "admin_worker_contexts",
                "admin_worker_skills",
                "admin_worker_capabilities",
                "admin_project_agents",
            ]
        }
    finally:
        con.close()

    assert counts == {
        "admin_worker_catalog": 0,
        "admin_worker_versions": 0,
        "admin_worker_contexts": 0,
        "admin_worker_skills": 0,
        "admin_worker_capabilities": 0,
        "admin_project_agents": 0,
    }


def test_gateway_templates_hard_delete_keeps_default_protected(
    gateway_admin_client,
) -> None:
    headers = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"}

    default_response = gateway_admin_client.delete(
        "/api/v1/admin/templates/default/hard-delete",
        headers=headers,
    )

    assert default_response.status_code == 403


def test_get_visible_worker_for_actor_accepts_boolean_active_rows(gateway_db: Path) -> None:
    from duckclaw import DuckClaw
    from duckclaw.admin_worker_catalog import create_worker, get_visible_worker_for_actor

    db = DuckClaw(str(gateway_db), read_only=False, engine="python")
    try:
        create_worker(
            db,
            owner_email="admin@test.local",
            worker_id="bi-analyst",
            display_name="AXIS Maestro",
        )
        worker = get_visible_worker_for_actor(
            db,
            actor_email="admin@test.local",
            worker_id="bi-analyst",
        )
    finally:
        db.close()

    assert worker is not None
    assert worker["worker_id"] == "bi-analyst"


def test_gateway_rejects_default_template_deactivation_explicitly(gateway_admin_client) -> None:
    response = gateway_admin_client.delete(
        "/api/v1/admin/templates/default",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
    )

    assert response.status_code == 403
    assert response.json()["detail"]["title"] == "Plantilla protegida"


def test_gateway_forge_projects_are_retired(gateway_admin_client) -> None:
    headers = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"}

    listed = gateway_admin_client.get("/api/v1/admin/forge-projects", headers=headers)
    created = gateway_admin_client.post(
        "/api/v1/admin/forge-projects",
        headers=headers,
        json={"id": "legacy", "members": ["default"]},
    )
    applied = gateway_admin_client.post(
        "/api/v1/admin/forge-projects/legacy/apply-team",
        headers=headers,
    )

    assert listed.status_code == 410
    assert created.status_code == 410
    assert applied.status_code == 410


def test_gateway_filesystem_template_actions_are_retired(gateway_admin_client) -> None:
    headers = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"}

    created = gateway_admin_client.post(
        "/api/v1/admin/templates",
        headers=headers,
        json={"id": "legacy-template", "source_template": "default"},
    )
    vault_binding = gateway_admin_client.put(
        "/api/v1/admin/templates/default/vault-binding",
        headers=headers,
        json={"scope": "private", "vault_id": "123"},
    )
    validated = gateway_admin_client.post(
        "/api/v1/admin/templates/default/validate",
        headers=headers,
    )

    assert created.status_code == 410
    assert vault_binding.status_code == 410
    assert validated.status_code == 410


def test_gateway_env_patch_is_retired(gateway_admin_client) -> None:
    response = gateway_admin_client.patch(
        "/api/v1/admin/env",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
        json={"values": {"DUCKCLAW_LLM_PROVIDER": "deepseek"}},
    )

    assert response.status_code == 410


def test_gateway_template_detail_rejects_unassigned_filesystem_template(
    gateway_admin_client,
) -> None:
    response = gateway_admin_client.get(
        "/api/v1/admin/templates/BI-Analyst",
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
    assert "default" not in workers
    assert workers["axis-coder"]["label"] == "AXIS Coder"
    assert "BI-Analyst" not in workers


def test_admin_health_uses_actor_visible_db_first_workers(
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
        create_worker(
            db,
            owner_email="other@test.local",
            worker_id="axis-other",
            display_name="Other Worker",
        )
    finally:
        db.close()

    response = gateway_admin_client.get(
        "/api/v1/admin/health",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["workers_count"] == 1
    assert set(data["workers"]) == {"axis-coder"}


def test_playground_llm_scope_does_not_report_legacy(gateway_admin_client) -> None:
    response = gateway_admin_client.get(
        "/api/v1/admin/playground/config",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
    )

    assert response.status_code == 200
    assert response.json()["llm"]["scope"] != "legacy"


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
        set_tenant_team_templates(db, profile["tenant_id"], ["BI-Analyst", "BI-Analyst"])
        create_worker(
            db,
            owner_email="admin@test.local",
            worker_id="bi-analyst",
            display_name="ANALISTA",
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
    assert "bi-analyst" in ids
    assert "axis-radar" in ids
    assert "BI-Analyst" not in ids
    assert "BI-Analyst" not in ids
    assert len(ids) == len(set(ids))


def test_playground_chat_rejects_unassigned_filesystem_worker_before_execution(
    gateway_admin_client,
) -> None:
    response = gateway_admin_client.post(
        "/api/v1/admin/playground/chat",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
        json={"worker_id": "BI-Analyst", "message": "hola"},
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
    import routers.admin_domains.playground.chat_turn as playground_chat_turn

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

    captured: dict[str, str] = {}

    async def _fake_invoke(_chat, worker_id, **_kwargs):
        captured["message"] = _chat.message
        return {"response": f"ok:{worker_id}", "assigned_worker_id": worker_id}

    monkeypatch.setattr(playground_chat_turn, "invoke_chat", _fake_invoke)

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
    assert "[PROJECT_CONTEXT]" in captured["message"]
    assert "Operación AXIS" in captured["message"]
    assert "Scope para Playground" in captured["message"]
    assert "hola" in captured["message"]

    default_project_chat = gateway_admin_client.post(
        "/api/v1/admin/playground/chat",
        headers=headers,
        json={
            "project_id": project["project_id"],
            "worker_id": "default",
            "message": "guíame",
            "chat_id": "project-orchestrator-playground",
        },
    )
    assert default_project_chat.status_code == 200
    assert default_project_chat.json()["project_id"] == project["project_id"]
    assert default_project_chat.json()["worker_id"] == "axis-radar"
    assert "[PROJECT_CONTEXT]" in captured["message"]
    assert "Operación AXIS" in captured["message"]
    assert "AXIS Radar" not in captured["message"]
    assert "axis-radar" in captured["message"]
    assert "guíame" in captured["message"]

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
