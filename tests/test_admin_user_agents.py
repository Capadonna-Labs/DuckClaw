from __future__ import annotations

from pathlib import Path

import duckdb


class _Adapter:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def execute(self, sql: str, params=None):
        if params is not None:
            return self._con.execute(sql, params)
        return self._con.execute(sql)


def test_user_agents_are_tenant_scoped_and_include_default(
    gateway_db: Path, tmp_path: Path, monkeypatch
) -> None:
    from duckclaw.admin_user_agents import create_runtime_agent, list_user_agents
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    monkeypatch.setenv("DUCKCLAW_RUNTIME_AGENTS_DIR", str(tmp_path / "runtime-agents"))

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        alice = ensure_profile_for_user(adapter, email="alice@test.local")
        bob = ensure_profile_for_user(adapter, email="bob@test.local")
        created = create_runtime_agent(
            adapter,
            owner_email="alice@test.local",
            worker_id="sales_bot",
            display_name="Sales Bot",
            source_template_id="default",
        )
        alice_agents = list_user_agents(adapter, "alice@test.local")
        bob_agents = list_user_agents(adapter, "bob@test.local")
    finally:
        con.close()

    assert created["tenant_id"] == alice["tenant_id"]
    assert created["manifest_path"].startswith(str(tmp_path / "runtime-agents"))
    assert "packages/agents/src/duckclaw/forge/templates" not in created["manifest_path"]
    assert {a["worker_id"] for a in alice_agents} == {"default", "sales_bot"}
    assert {a["worker_id"] for a in bob_agents} == {"default"}
    assert alice["tenant_id"] != bob["tenant_id"]


def test_runtime_agent_rejects_duplicate_per_tenant(gateway_db: Path, tmp_path: Path, monkeypatch) -> None:
    import pytest

    from duckclaw.admin_user_agents import create_runtime_agent
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    monkeypatch.setenv("DUCKCLAW_RUNTIME_AGENTS_DIR", str(tmp_path / "runtime-agents"))

    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        ensure_profile_for_user(adapter, email="alice@test.local")
        create_runtime_agent(
            adapter,
            owner_email="alice@test.local",
            worker_id="sales_bot",
            display_name="Sales Bot",
            source_template_id="default",
        )
        with pytest.raises(ValueError, match="ya existe"):
            create_runtime_agent(
                adapter,
                owner_email="alice@test.local",
                worker_id="sales_bot",
                display_name="Sales Bot 2",
                source_template_id="default",
            )
    finally:
        con.close()


def test_user_agent_endpoint_creates_runtime_agent_and_playground_lists_it(
    gateway_admin_client, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setenv("DUCKCLAW_RUNTIME_AGENTS_DIR", str(tmp_path / "runtime-agents"))
    headers = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"}

    created = gateway_admin_client.post(
        "/api/v1/admin/user-agents",
        headers=headers,
        json={
            "worker_id": "sales_bot",
            "display_name": "Sales Bot",
            "source_template_id": "default",
            "system_prompt": "Ayuda con ventas consultivas.",
            "description": "Agente de ventas",
            "skills": ["crm"],
        },
    )
    assert created.status_code == 200
    row = created.json()["agent"]
    assert row["worker_id"] == "sales_bot"
    assert row["manifest_path"].startswith(str(tmp_path / "runtime-agents"))
    assert "packages/agents/src/duckclaw/forge/templates" not in row["manifest_path"]

    cfg = gateway_admin_client.get("/api/v1/admin/playground/config", headers=headers)
    assert cfg.status_code == 200
    workers = {w["id"]: w for w in cfg.json()["workers"]}
    assert "default" in workers
    assert workers["sales_bot"]["label"] == "Sales Bot"
