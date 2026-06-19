"""Manager invoke helpers — project_id propagation for RAG tools."""

from __future__ import annotations

from duckclaw.manager.manager_invoke_helpers import prepare_worker_invoke_state


def test_prepare_worker_invoke_state_propagates_project_id() -> None:
    state = {
        "project_id": "prj_aws_expert",
        "username": "admin@test.local",
    }
    worker_state = prepare_worker_invoke_state(
        state=state,
        planned_task_for_worker="Busca en RAG",
        incoming="que conocimiento tienes",
        history=[],
        chat_id="admin-playground",
        tenant_id="default",
        user_id="admin-ui",
        vault_db_path="/tmp/session.duckdb",
        shared_db_path="",
        agent_instance_label="aws-expert-agent",
        plan_title=None,
        pa=0,
        max_a=1,
        assigned="aws-expert-agent",
    )
    assert worker_state["project_id"] == "prj_aws_expert"


def test_prepare_worker_invoke_state_omits_empty_project_id() -> None:
    worker_state = prepare_worker_invoke_state(
        state={"project_id": ""},
        planned_task_for_worker="hola",
        incoming="hola",
        history=[],
        chat_id="admin-playground",
        tenant_id="default",
        user_id="admin-ui",
        vault_db_path="",
        shared_db_path="",
        agent_instance_label="default",
        plan_title=None,
        pa=0,
        max_a=1,
        assigned="default",
    )
    assert "project_id" not in worker_state
