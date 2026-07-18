"""Tests for GET /api/v1/admin/workers/{worker_id}/capabilities."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def test_worker_capabilities_requires_admin_key(admin_client: TestClient) -> None:
    response = admin_client.get("/api/v1/admin/workers/default/capabilities")
    assert response.status_code == 401


def test_worker_capabilities_default_scaffold(admin_client: TestClient) -> None:
    response = admin_client.get(
        "/api/v1/admin/workers/default/capabilities",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["worker_id"] == "default"
    assert data["skills_declared"] == []
    assert data["skills_effective"] == []
    assert data["framework_baseline"] is False
    assert isinstance(data["tools_runtime"], list)
    assert data["sandbox"]["session_enabled"] is None
    assert "registered" in data["sandbox"]
    assert "docker_ok" in data["sandbox"]
    assert isinstance(data["optional"], dict)
    assert isinstance(data["gaps"], list)
    assert isinstance(data.get("integration_gaps"), list)


def test_worker_capabilities_reports_sandbox_when_registered(
    admin_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "duckclaw.graphs.sandbox._docker_available",
        lambda: True,
    )

    response = admin_client.get(
        "/api/v1/admin/workers/default/capabilities",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert response.status_code == 200
    data = response.json()
    if data["sandbox"]["registered"]:
        assert "run_sandbox" in data["tools_runtime"]


def test_worker_capabilities_gaps_skip_report_engine_homonym() -> None:
    from routers.admin_domains.worker_capabilities import _compute_gaps

    gaps, _ = _compute_gaps(
        skills_effective=["report_engine", "get_current_time", "read_sql"],
        tools_runtime=[
            "get_current_time",
            "read_sql",
            "list_report_templates",
            "register_report_template",
            "create_report_instance",
            "list_report_instances",
            "create_blank_document",
            "get_report_status",
            "patch_report_section",
            "patch_report_image",
            "render_report_instance",
            "generate_report_docx_from_markdown",
        ],
        sandbox_registered=False,
        docker_ok=True,
        manifest_data={"framework_baseline": False},
        optional={},
    )
    assert not any("sin tool homónima" in g and "report_engine" in g for g in gaps)
    assert not any("sin tools de Report Engine" in g for g in gaps)
    assert not any("get_current_time" in g and "no registrada" in g for g in gaps)


def test_worker_capabilities_gaps_sandbox_alias_and_mcp_github() -> None:
    from routers.admin_domains.worker_capabilities import _compute_gaps

    gaps, integration = _compute_gaps(
        skills_effective=[
            "execute_sandbox_script",
            "github",
            "notion",
            "propose_code_change",
            "convert_document",
            "openweather",
            "research",
        ],
        tools_runtime=["run_sandbox", "mcp__github__get_me", "read_sql"],
        sandbox_registered=True,
        docker_ok=True,
        manifest_data={"framework_baseline": False},
        optional={"tavily": False},
        db=None,
    )
    assert not any("execute_sandbox_script" in g for g in gaps)
    assert not any("github" in g and "sin tool" in g for g in gaps)
    assert not any("convert_document" in g for g in gaps)
    assert not any("propose_code_change" in g for g in gaps)
    assert not any("notion" in g for g in gaps)
    assert not any("falta API key" in g for g in gaps)
    # openweather/research siguen en integration_gaps para el editor de plantilla
    assert isinstance(integration, list)


def test_worker_capabilities_not_found(admin_client: TestClient) -> None:
    response = admin_client.get(
        "/api/v1/admin/workers/does-not-exist-xyz/capabilities",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert response.status_code == 404
    detail = response.json().get("detail") or {}
    assert detail.get("status") == 404


def test_worker_mcp_grants_requires_admin_key(admin_client: TestClient) -> None:
    response = admin_client.get("/api/v1/admin/workers/default/mcp-grants")
    assert response.status_code == 401


def test_worker_mcp_grants_default_scaffold(admin_client: TestClient) -> None:
    response = admin_client.get(
        "/api/v1/admin/workers/default/mcp-grants",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["worker_id"] == "default"
    assert isinstance(data["connectors"], list)
