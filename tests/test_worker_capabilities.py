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
            "get_report_status",
            "patch_report_section",
            "render_report_instance",
            "generate_report_docx_from_markdown",
        ],
        sandbox_registered=False,
        docker_ok=True,
        manifest_data={"framework_baseline": False},
        optional={},
    )
    assert not any("sin tool homónima" in g and "report_engine" in g for g in gaps)
    assert not any("get_current_time" in g and "no registrada" in g for g in gaps)


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
