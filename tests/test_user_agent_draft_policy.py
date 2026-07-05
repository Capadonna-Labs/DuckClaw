"""User-agent draft policy seed and coalesce behavior."""

from __future__ import annotations

import json

import duckdb
import pytest

from duckclaw.user_agent_draft_policy import apply_user_agent_draft_policy


def test_apply_user_agent_draft_policy_v2(gateway_db) -> None:
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(str(gateway_db))
    try:
        run_pending_migrations(con)
        changed = apply_user_agent_draft_policy(con, force=True)
        assert changed is True
        row = con.execute(
            """
            SELECT content, active
            FROM main.prompt_policy_registry
            WHERE policy_type = 'manager_task' AND policy_name = 'admin_user_agent_draft'
            ORDER BY version DESC
            LIMIT 1
            """
        ).fetchone()
        assert row is not None
        assert row[1] is True
        parsed = json.loads(str(row[0]))
        assert "draft_prompt_template" in parsed
        assert "fallback" in parsed
        assert "system_prompt_template" in parsed["fallback"]
        assert "soul_template" in parsed["fallback"]
        assert "mínimo 400 caracteres" in parsed["draft_prompt_template"]
    finally:
        con.close()


def test_sanitize_wizard_questions_drops_jargon_when_prompt_is_clear() -> None:
    from duckclaw.user_agent_draft_policy import sanitize_wizard_questions

    assert sanitize_wizard_questions(
        "Agente DevOps que revisa logs PM2 y propone fixes",
        ["¿Qué fuentes (DB, vault, sandbox, web) debe usar con prioridad?"],
    ) == []
    assert sanitize_wizard_questions(
        "corto",
        ["¿Para quién es este asistente?"],
    ) == ["¿Para quién es este asistente?"]


def test_coalesce_draft_from_fallback_fills_short_fields() -> None:
    from duckclaw.user_agent_draft_policy import coalesce_user_agent_draft

    fallback = {
        "display_name": "Asistente DevOps",
        "worker_id": "devops-agent",
        "description": "Agente especializado en DevOps.",
        "system_prompt": "## Rol y objetivo\n" + ("Instrucción detallada. " * 12),
        "soul": "## Tono\nDirecto y verificable.\n\n## Estilo\nPrioriza evidencia.",
        "tool_profile": "general",
    }
    merged = coalesce_user_agent_draft(
        {
            "display_name": "",
            "worker_id": "",
            "description": "",
            "system_prompt": "corto",
            "soul": "x",
            "tool_profile": "general",
        },
        fallback,
        normalize_tool_profile=lambda raw: raw if raw in {"general", "minimal", "rag_only"} else "general",
    )
    assert merged["display_name"] == "Asistente DevOps"
    assert merged["worker_id"] == "devops-agent"
    assert len(merged["system_prompt"]) >= 80
    assert len(merged["soul"]) >= 20


def test_user_agent_draft_confirm_rejects_short_prompt(
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
    draft["system_prompt"] = "demasiado corto"
    draft["soul"] = "ok"

    confirm = gateway_admin_client.post(
        "/api/v1/admin/user-agents/draft/confirm",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "alice@test.local"},
        json={"draft": draft},
    )
    assert confirm.status_code == 400


def test_user_agent_confirm_materializes_prompt_policy_and_files(
    gateway_db,
    gateway_admin_client,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("duckclaw.db_write_queue.spawn_inline_writes_enabled", lambda: True)
    draft_response = gateway_admin_client.post(
        "/api/v1/admin/user-agents/draft",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "alice@test.local"},
        json={
            "prompt": "Agente DevOps que revisa logs PM2, diagnostica gateway y propone fixes en sandbox",
            "display_name": "Marco DevOps",
        },
    )
    assert draft_response.status_code == 200, draft_response.text
    draft = draft_response.json()
    draft["worker_id"] = "marco-devops-agent"
    assert len(draft["system_prompt"]) >= 80
    assert len(draft.get("soul") or "") >= 20

    confirm = gateway_admin_client.post(
        "/api/v1/admin/user-agents/draft/confirm",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "alice@test.local"},
        json={"draft": draft},
    )
    assert confirm.status_code == 200, confirm.text

    con = duckdb.connect(str(gateway_db))
    try:
        policy = con.execute(
            """
            SELECT active FROM main.prompt_policy_registry
            WHERE policy_type = 'system_prompt' AND policy_name = 'marco-devops-agent'
            ORDER BY version DESC LIMIT 1
            """
        ).fetchone()
        files = con.execute(
            """
            SELECT v.files_snapshot_json
            FROM main.admin_worker_versions v
            JOIN main.admin_worker_catalog w ON w.worker_uid = v.worker_uid
            WHERE w.worker_id = 'marco-devops-agent'
            ORDER BY v.version DESC LIMIT 1
            """
        ).fetchone()
        soul_ctx = con.execute(
            """
            SELECT c.title FROM main.admin_worker_contexts c
            JOIN main.admin_worker_catalog w ON w.worker_uid = c.worker_uid
            WHERE w.worker_id = 'marco-devops-agent' AND c.title = 'soul.md'
            """
        ).fetchone()
    finally:
        con.close()

    assert policy is not None and policy[0] is True
    snapshot = json.loads(str(files[0]))
    assert "system_prompt.md" in snapshot
    assert "soul.md" in snapshot
    assert soul_ctx is not None
