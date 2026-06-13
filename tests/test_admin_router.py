"""Tests Admin API router (spec: DuckClaw_Admin_UI)."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from env_ids import (
    DEFAULT_TEST_TELEGRAM_USER_ID,
    DEFAULT_TEST_TELEGRAM_USER_ID_ALT,
)


def _playground_worker_ids(data: dict) -> list[str]:
    """``workers`` en playground/config: ``[{id, label}, ...]`` o legacy ``[str, ...]``."""
    ids: list[str] = []
    for w in data.get("workers") or []:
        if isinstance(w, dict):
            wid = (w.get("id") or "").strip()
            if wid:
                ids.append(wid)
        elif isinstance(w, str) and w.strip():
            ids.append(w.strip())
    return ids


def test_admin_requires_key(admin_client: TestClient):
    r = admin_client.get("/api/v1/admin/health")
    assert r.status_code == 401


def test_admin_health_ok(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/health",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "ok"
    assert "workers_count" in data


def test_list_templates(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/templates",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    assert "templates" in r.json()


def test_fly_commands(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/fly-commands",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "commands" in data
    assert isinstance(data["commands"], list)
    assert any(c.get("cmd") == "/team" for c in data["commands"])


def test_admin_audit_empty(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/audit",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    assert "entries" in r.json()


def test_catalog_skills(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/catalog/skills",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "global" in data
    assert "template_local" in data


def test_catalog_skills_does_not_expose_filesystem_skills_without_db_rows(
    gateway_admin_client: TestClient,
) -> None:
    response = gateway_admin_client.get(
        "/api/v1/admin/catalog/skills",
        headers={
            "X-Admin-Key": "test-admin-key",
            "X-Duckclaw-Actor": "admin@test.local",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["global"] == []
    assert data["template_local"] == []


def test_catalog_skills_global_are_scoped_to_authenticated_db_skills(
    gateway_admin_client: TestClient,
    gateway_db: Path,
) -> None:
    import duckdb
    from duckclaw.admin_user_profiles import ensure_profile_for_user
    from duckclaw.admin_worker_catalog import register_skill

    con = duckdb.connect(str(gateway_db))
    try:
        class _A:
            def execute(self, sql: str, params=None):
                if params is not None:
                    return con.execute(sql, params)
                return con.execute(sql)

        adapter = _A()
        profile = ensure_profile_for_user(adapter, email="admin@test.local")
        register_skill(
            adapter,
            name="my_db_skill",
            skill_type="python",
            implementation_ref="db://skills/my_db_skill.py",
            owner_email=profile["email"],
            tenant_id=profile["tenant_id"],
        )
    finally:
        con.close()

    response = gateway_admin_client.get(
        "/api/v1/admin/catalog/skills",
        headers={
            "X-Admin-Key": "test-admin-key",
            "X-Duckclaw-Actor": "admin@test.local",
        },
    )
    assert response.status_code == 200
    global_skills = response.json().get("global") or []
    assert global_skills == [
        {
            "id": "my_db_skill",
            "path": "db://skills/my_db_skill.py",
            "scope": "catalog",
        }
    ]


def test_create_catalog_skill_for_authenticated_actor(
    gateway_admin_client: TestClient,
) -> None:
    response = gateway_admin_client.post(
        "/api/v1/admin/catalog/skills",
        headers={
            "X-Admin-Key": "test-admin-key",
            "X-Duckclaw-Actor": "admin@test.local",
        },
        json={
            "name": "customer_lookup",
            "description": "Consulta datos de clientes desde una API controlada.",
            "skill_type": "python",
            "implementation_ref": "db://skills/customer_lookup.py",
        },
    )
    assert response.status_code == 200
    created = response.json()["skill"]
    assert created["id"] == "customer_lookup"
    assert created["path"] == "db://skills/customer_lookup.py"
    assert created["scope"] == "catalog"

    listed = gateway_admin_client.get(
        "/api/v1/admin/catalog/skills",
        headers={
            "X-Admin-Key": "test-admin-key",
            "X-Duckclaw-Actor": "admin@test.local",
        },
    )
    assert listed.status_code == 200
    assert created in listed.json()["global"]


def test_catalog_skills_local_are_scoped_to_authenticated_catalog_workers(
    gateway_admin_client: TestClient,
    gateway_db: Path,
) -> None:
    import duckdb
    from duckclaw.admin_worker_catalog import add_worker_version, create_worker

    con = duckdb.connect(str(gateway_db))
    try:
        class _A:
            def execute(self, sql: str, params=None):
                if params is not None:
                    return con.execute(sql, params)
                return con.execute(sql)

        adapter = _A()
        worker = create_worker(
            adapter,
            owner_email="admin@test.local",
            worker_id="custom-bi",
            display_name="Custom BI",
        )
        add_worker_version(
            adapter,
            worker_uid=worker["worker_uid"],
            created_by="admin@test.local",
            files_snapshot={
                "skills/my_private_skill.py": "def build_tools(): return []",
                "system_prompt.md": "# prompt",
            },
        )
    finally:
        con.close()

    response = gateway_admin_client.get(
        "/api/v1/admin/catalog/skills",
        headers={
            "X-Admin-Key": "test-admin-key",
            "X-Duckclaw-Actor": "admin@test.local",
        },
    )
    assert response.status_code == 200
    local = response.json().get("template_local") or []
    assert any(item["worker_id"] == "custom-bi" and item["id"] == "my_private_skill" for item in local)
    assert not any(item.get("worker_id") == "BI-Analyst" for item in local)


def test_playground_config(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/playground/config",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "llm" in data
    assert "catalog" in data
    assert "workers" in data
    assert isinstance(data.get("workers"), list)
    assert "authorized" in data
    assert "team_chat_id" in data
    assert data.get("chat_endpoint") == "/api/v1/admin/playground/chat"


def test_playground_config_team_for_telegram_chat(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch, catalog_db):
    from duckclaw import DuckClaw
    from duckclaw.workers.factory import list_workers

    all_w = list_workers(db=catalog_db, tenant_id="default")
    if not all_w:
        pytest.skip("need templates")
    target = all_w[0]
    monkeypatch.setenv("DUCKCLAW_OWNER_ID", DEFAULT_TEST_TELEGRAM_USER_ID)
    gw_dir = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
    import sys

    if str(gw_dir) not in sys.path:
        sys.path.insert(0, str(gw_dir))
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "pg_team.duckdb")
        db = DuckClaw(db_path, read_only=False, engine="python")
        from duckclaw.graphs.on_the_fly_commands import set_team_templates

        set_team_templates(db, DEFAULT_TEST_TELEGRAM_USER_ID, [target])
        db.close()
        monkeypatch.setenv("DUCKDB_PATH", db_path)
        monkeypatch.setattr("duckclaw.gateway_db.get_gateway_db_path", lambda: db_path)
        r = admin_client.get(
            "/api/v1/admin/playground/config",
            headers={"X-Admin-Key": "test-admin-key"},
            params={
                "telegram_user_id": DEFAULT_TEST_TELEGRAM_USER_ID,
                "tenant_id": "default",
            },
        )
    assert r.status_code == 200
    data = r.json()
    assert data.get("authorized") is True
    from duckclaw.workers.identity import normalize_worker_id

    assert normalize_worker_id(target) in _playground_worker_ids(data)
    assert data.get("team_source") == "chat"


def _mock_playground_team(*, workers: list[str], authorized: bool = True) -> dict:
    return {
        "workers": workers,
        "authorized": authorized,
        "team_chat_id": "admin-playground",
        "telegram_user_id": "test-owner",
        "tenant_id": "default",
        "whitelist_role": "owner",
        "team_source": "chat",
        "team_hint": "mock",
    }


def test_playground_chat(admin_client: TestClient, gateway_db: Path, monkeypatch: pytest.MonkeyPatch):
    gw_dir = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
    import sys

    if str(gw_dir) not in sys.path:
        sys.path.insert(0, str(gw_dir))
    import main as gateway_main
    import routers.admin as admin_router
    from duckclaw import DuckClaw
    from duckclaw.admin_worker_catalog import create_worker

    async def _fake_invoke(*_args, **_kwargs):
        return {"response": "respuesta-mock", "usage_tokens": {"total": 1}}

    monkeypatch.setattr(
        admin_router,
        "_playground_team_context",
        lambda **_: _mock_playground_team(workers=["axis-maestro"]),
    )
    monkeypatch.setattr(gateway_main, "_invoke_chat", _fake_invoke)
    db = DuckClaw(str(gateway_db), read_only=False, engine="python")
    try:
        create_worker(
            db,
            owner_email="admin@test.local",
            worker_id="axis-maestro",
            display_name="AXIS Maestro",
        )
    finally:
        db.close()
    r = admin_client.post(
        "/api/v1/admin/playground/chat",
        headers={"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"},
        json={"worker_id": "axis-maestro", "message": "hola"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert data.get("response") == "respuesta-mock"
    assert data.get("worker_id") == "axis-maestro"


def test_playground_chat_rejects_worker_outside_team(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch
):
    gw_dir = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
    import sys

    if str(gw_dir) not in sys.path:
        sys.path.insert(0, str(gw_dir))
    import routers.admin as admin_router

    monkeypatch.setattr(
        admin_router,
        "_playground_team_context",
        lambda **_: _mock_playground_team(workers=["default"]),
    )
    r = admin_client.post(
        "/api/v1/admin/playground/chat",
        headers={"X-Admin-Key": "test-admin-key"},
        json={"worker_id": "AXIS-Maestro", "message": "hola"},
    )
    assert r.status_code == 403


def test_playground_chat_no_tailscale_key(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("DUCKCLAW_TAILSCALE_AUTH_KEY", "ts-required")
    gw_dir = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
    import sys

    if str(gw_dir) not in sys.path:
        sys.path.insert(0, str(gw_dir))
    import main as gateway_main
    import routers.admin as admin_router

    async def _fake_invoke(*_args, **_kwargs):
        return {"response": "ok"}

    monkeypatch.setattr(
        admin_router,
        "_playground_team_context",
        lambda **_: _mock_playground_team(workers=["default"]),
    )
    monkeypatch.setattr(gateway_main, "_invoke_chat", _fake_invoke)
    r = admin_client.post(
        "/api/v1/admin/playground/chat",
        headers={"X-Admin-Key": "test-admin-key"},
        json={"worker_id": "default", "message": "ping"},
    )
    assert r.status_code == 200
    assert r.json().get("response") == "ok"


def test_invoke_chat_admin_console_delivery_bypasses_telegram_guard(monkeypatch: pytest.MonkeyPatch):
    gw_dir = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
    import sys

    if str(gw_dir) not in sys.path:
        sys.path.insert(0, str(gw_dir))
    import main as gateway_main
    from core.models import ChatRequest
    from duckclaw.channels import GatewayDeliveryContext

    async def _fail_if_called(**_kwargs):
        raise AssertionError("Telegram Guard should not run for authenticated admin console delivery")

    monkeypatch.setattr(gateway_main, "_authorize_or_reject", _fail_if_called)

    result = __import__("asyncio").run(
        gateway_main._invoke_chat(
            ChatRequest(
                message="",
                chat_id="admin-conv-test",
                user_id="console@example.test",
                username="console@example.test",
                chat_type="private",
            ),
            "default",
            "admin-conv-test",
            "user-console-tenant",
            delivery_context=GatewayDeliveryContext.trusted_admin_console(),
        )
    )
    assert "No recibí ningún mensaje" in result["response"]


def test_template_vault_options_and_put(
    admin_client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    gw_dir = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
    import sys

    if str(gw_dir) not in sys.path:
        sys.path.insert(0, str(gw_dir))
    import routers.admin as admin_router

    templates_root = tmp_path / "forge" / "templates"
    wid = "VaultTestWorker"
    worker_dir = templates_root / wid
    worker_dir.mkdir(parents=True)
    (worker_dir / "manifest.yaml").write_text(
        "name: VaultTest\nid: vault_test\nschema_name: main\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(admin_router, "_templates_dir", lambda: templates_root)
    try:
        from duckclaw.forge import WORKERS_TEMPLATES_DIR as _wtd

        monkeypatch.setattr("duckclaw.forge.WORKERS_TEMPLATES_DIR", templates_root)
        monkeypatch.setattr("duckclaw.workers.manifest.WORKERS_TEMPLATES_DIR", templates_root, raising=False)
    except ImportError:
        pass
    priv = tmp_path / "db" / "private" / "alice"
    priv.mkdir(parents=True)
    (priv / "custom.duckdb").write_bytes(b"x" * 8)

    r = admin_client.get(
        f"/api/v1/admin/templates/{wid}/vault-options",
        headers={"X-Admin-Key": "test-admin-key"},
        params={"vault_user_id": "alice"},
    )
    assert r.status_code == 200
    opts = r.json().get("options") or []
    assert any(o.get("vault_id") == "custom" for o in opts)

    r2 = admin_client.put(
        f"/api/v1/admin/templates/{wid}/vault-binding",
        headers={"X-Admin-Key": "test-admin-key"},
        json={"scope": "private", "vault_id": "custom"},
    )
    assert r2.status_code == 410

    manifest_text = (worker_dir / "manifest.yaml").read_text(encoding="utf-8")
    assert "vault_binding" not in manifest_text
    assert "custom" not in manifest_text


def test_catalog_topologies(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/catalog/topologies",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    ids = [t["id"] for t in r.json().get("topologies") or []]
    assert "general" in ids
    assert "orchestrator" in ids


def test_catalog_mcp(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/catalog/mcp",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "duckclaw_mcp" in data
    assert "tools" in data["duckclaw_mcp"]
    assert "live" in data["duckclaw_mcp"]
    assert data["duckclaw_mcp"]["runtime_key"] == "mcp.port"
    assert data["duckclaw_mcp"]["port"] == "8001"
    assert data["duckclaw_mcp"]["source"] in {"default", "env", "db"}
    official = data.get("official_reference") or {}
    servers = official.get("servers") or []
    assert len(servers) >= 7
    ids = {s.get("id") for s in servers}
    assert "memory" in ids
    assert "git" in ids
    assert official.get("source_repo", "").startswith("https://github.com/modelcontextprotocol/servers")


def test_ops_commands(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/ops/commands",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    cmds = r.json().get("commands") or []
    assert any(c.get("id") == "pm2_list" for c in cmds)
    assert any(c.get("id") == "pm2_start_mcp" for c in cmds)


def test_normalize_pm2_gateway_restart_interrupted(admin_client: TestClient):
    from routers.admin import _normalize_ops_result

    raw = {
        "exit_code": -2,
        "stdout": "[PM2] Applying action restartProcessId on app [DuckClaw-Gateway](ids: [ 0 ])\n",
        "stderr": "",
    }
    out = _normalize_ops_result("pm2_restart_gateway", raw)
    assert out["exit_code"] == 0


def test_telegram_routes_get_and_put(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    env_file = tmp_path / ".env"
    compact_line = "mybot:tok1:/api/v1/telegram/mybot:Worker-A:TenantA"
    env_file.write_text(
        f"DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES={compact_line}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES", compact_line)

    import routers.admin as admin_router

    monkeypatch.setattr(admin_router, "_env_file", lambda: env_file)

    r = admin_client.get(
        "/api/v1/admin/telegram/routes",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("format") == "compact"
    assert data.get("source") == "env"
    assert len(data.get("routes") or []) == 1
    assert data["routes"][0]["bot"] == "mybot"
    assert data["routes"][0]["worker_id"] == "Worker-A"

    r2 = admin_client.put(
        "/api/v1/admin/telegram/routes",
        headers={"X-Admin-Key": "test-admin-key"},
        json={
            "routes": [
                {
                    "bot": "mybot",
                    "path": "/api/v1/telegram/mybot",
                    "worker_id": "Worker-A",
                    "tenant_id": "TenantA",
                },
                {
                    "bot": "other",
                    "path": "/api/v1/telegram/other",
                    "worker_id": "Worker-B",
                    "tenant_id": "TenantB",
                    "token": "tok_other",
                },
            ]
        },
    )
    assert r2.status_code == 200
    assert r2.json().get("route_count") == 2
    assert r2.json().get("source") == "db"
    saved = env_file.read_text(encoding="utf-8")
    assert "other:tok_other:/api/v1/telegram/other:Worker-B:TenantB" not in saved
    assert "mybot:tok1:/api/v1/telegram/mybot:Worker-A:TenantA" in saved

    r3 = admin_client.get(
        "/api/v1/admin/telegram/routes",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r3.status_code == 200
    data3 = r3.json()
    assert data3.get("source") == "db"
    assert len(data3.get("routes") or []) == 2
    assert {row["bot"] for row in data3["routes"]} == {"mybot", "other"}


def test_telegram_whitelist_get(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/telegram/whitelist?tenant_id=default",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("tenant_id") == "default"
    assert "users" in data


def test_telegram_whitelist_resolves_gateway_tenant(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    """default en UI → tenant efectivo del gateway (p. ej. Marco vía DUCKCLAW_GATEWAY_TENANT_ID)."""
    monkeypatch.setenv("DUCKCLAW_GATEWAY_TENANT_ID", "test-tenant")
    dbf = tmp_path / "hub.duckdb"
    monkeypatch.setattr(
        "duckclaw.gateway_db.get_gateway_db_path",
        lambda: str(dbf),
    )
    import duckdb

    con = duckdb.connect(str(dbf))
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS main.authorized_users (
            tenant_id VARCHAR, user_id VARCHAR, username VARCHAR,
            role VARCHAR DEFAULT 'user', added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (tenant_id, user_id)
        );
        INSERT INTO main.authorized_users (tenant_id, user_id, username, role)
        VALUES ('default', ?, 'legacy', 'user');
        """,
        [DEFAULT_TEST_TELEGRAM_USER_ID_ALT],
    )
    con.close()

    r = admin_client.get(
        "/api/v1/admin/telegram/whitelist?tenant_id=default",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("effective_tenant_id") == "test-tenant"
    assert data.get("tenant_id") == "test-tenant"
    ids = [u["user_id"] for u in data.get("users") or []]
    assert DEFAULT_TEST_TELEGRAM_USER_ID_ALT in ids

    r2 = admin_client.post(
        "/api/v1/admin/telegram/whitelist",
        headers={"X-Admin-Key": "test-admin-key"},
        json={
            "tenant_id": "default",
            "user_id": DEFAULT_TEST_TELEGRAM_USER_ID,
            "username": "Owner",
            "role": "admin",
        },
    )
    assert r2.status_code == 200
    assert r2.json().get("tenant_id") == "test-tenant"

    con = duckdb.connect(str(dbf))
    row = con.execute(
        "SELECT tenant_id FROM main.authorized_users WHERE user_id = ?",
        [DEFAULT_TEST_TELEGRAM_USER_ID],
    ).fetchone()
    con.close()
    assert row is not None
    assert row[0] == "test-tenant"


def test_train_admin_routes_removed(admin_client: TestClient):
    headers = {"X-Admin-Key": "test-admin-key"}

    assert admin_client.get("/api/v1/admin/train/status", headers=headers).status_code == 404
    assert (
        admin_client.post(
            "/api/v1/admin/train/pipeline/collect",
            headers=headers,
            json={"require_valid_sql": False},
        ).status_code
        == 404
    )


def test_playground_team_hint_workers_label(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch, catalog_db):
    from duckclaw import DuckClaw
    from duckclaw.workers.factory import list_workers

    all_w = list_workers(db=catalog_db, tenant_id="default")
    if not all_w:
        pytest.skip("need templates")
    monkeypatch.setenv("DUCKCLAW_OWNER_ID", DEFAULT_TEST_TELEGRAM_USER_ID)
    gw_dir = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
    import sys

    if str(gw_dir) not in sys.path:
        sys.path.insert(0, str(gw_dir))
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "pg_hint.duckdb")
        db = DuckClaw(db_path, read_only=False, engine="python")
        from duckclaw.graphs.on_the_fly_commands import set_team_templates

        set_team_templates(db, DEFAULT_TEST_TELEGRAM_USER_ID, [all_w[0]])
        db.close()
        monkeypatch.setenv("DUCKDB_PATH", db_path)
        monkeypatch.setattr("duckclaw.gateway_db.get_gateway_db_path", lambda: db_path)
        r = admin_client.get(
            "/api/v1/admin/playground/config",
            headers={"X-Admin-Key": "test-admin-key"},
            params={"telegram_user_id": DEFAULT_TEST_TELEGRAM_USER_ID},
        )
    assert r.status_code == 200
    hint = r.json().get("team_hint") or ""
    assert "Equipo de este chat (/workers)" in hint
    assert "Telegram" not in hint


def test_kanban_worker_states(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from routers.admin import _kanban_status_from_audit

    assert _kanban_status_from_audit("SUCCESS", 900) == "en_progreso"
    assert _kanban_status_from_audit("SUCCESS", 4000) == "completo"
    assert _kanban_status_from_audit("FAILED", 4000 * 60) == "pendiente"

    r = admin_client.get(
        "/api/v1/admin/kanban/worker-states",
        headers={"X-Admin-Key": "test-admin-key"},
        params={"workers": "default,default"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "states" in data
    assert isinstance(data["states"], dict)


def test_kanban_swarm_slots(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    import duckclaw.graphs.subagent_run_id as subagent_mod

    def _fake_slots(tid: str, wids: list[str] | None) -> list[dict]:
        return [
            {
                "worker_id": "default",
                "slot": 1,
                "chat_scope": None,
                "started_at": 1.0,
                "active": True,
            },
            {
                "worker_id": "default",
                "slot": 2,
                "chat_scope": "123",
                "started_at": 2.0,
                "active": True,
            },
        ]

    monkeypatch.setattr(subagent_mod, "list_active_swarm_slots", _fake_slots)

    r = admin_client.get(
        "/api/v1/admin/kanban/swarm-slots",
        headers={"X-Admin-Key": "test-admin-key"},
        params={"workers": "default"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["instances"]
    assert data["states"]["default:1"] == "en_progreso"
    assert data["states"]["default:2"] == "en_progreso"


def test_kanban_cards_db_first_crud(
    admin_client: TestClient,
    gateway_db: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    import duckdb

    from duckclaw.schema_migrations import run_pending_migrations

    monkeypatch.setenv("DUCKCLAW_SPAWN_PROFILE", "1")
    con = duckdb.connect(str(gateway_db))
    try:
        run_pending_migrations(con)
    finally:
        con.close()

    headers = {
        "X-Admin-Key": "test-admin-key",
        "X-Duckclaw-Actor": "admin@test.local",
    }
    create = admin_client.post(
        "/api/v1/admin/kanban",
        headers=headers,
        json={
            "title": "Crear agente",
            "description": "Desde tablero",
            "status": "pendiente",
            "worker_id": "default",
            "tags": ["manual"],
        },
    )
    assert create.status_code == 200
    created = create.json()["card"]
    assert created["status"] == "pendiente"
    assert created["worker_id"] == "default"

    listing = admin_client.get("/api/v1/admin/kanban", headers=headers)
    assert listing.status_code == 200
    assert [c["id"] for c in listing.json()["cards"]] == [created["id"]]

    update = admin_client.patch(
        "/api/v1/admin/kanban",
        headers=headers,
        json={"id": created["id"], "status": "en_progreso", "title": "Crear agente DB"},
    )
    assert update.status_code == 200
    assert update.json()["card"]["status"] == "en_progreso"

    delete = admin_client.delete(f"/api/v1/admin/kanban?id={created['id']}", headers=headers)
    assert delete.status_code == 200
    assert delete.json()["ok"] is True

    empty = admin_client.get("/api/v1/admin/kanban", headers=headers)
    assert empty.status_code == 200
    assert empty.json()["cards"] == []


def test_prompt_policies_admin_crud_is_db_writer_backed(
    admin_client: TestClient,
    gateway_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import duckdb

    from duckclaw.prompt_policies import PromptPolicyResolver
    from duckclaw.schema_migrations import run_pending_migrations

    monkeypatch.setenv("DUCKCLAW_SPAWN_PROFILE", "1")
    con = duckdb.connect(str(gateway_db))
    try:
        run_pending_migrations(con)
    finally:
        con.close()

    headers = {
        "X-Admin-Key": "test-admin-key",
        "X-Duckclaw-Actor": "admin@test.local",
    }
    empty = admin_client.get(
        "/api/v1/admin/prompt-policies",
        headers=headers,
        params={"policy_type": "system_prompt"},
    )
    assert empty.status_code == 200
    assert empty.json()["policies"] == []

    upsert = admin_client.put(
        "/api/v1/admin/prompt-policies",
        headers=headers,
        json={
            "policy_type": "system_prompt",
            "policy_name": "rag_turn",
            "version": 1,
            "content": "Endpoint policy for {worker_id}.",
            "metadata": {"created_by_test": True},
        },
    )
    assert upsert.status_code == 200
    created = upsert.json()["policy"]
    assert upsert.json()["ok"] is True
    assert created["policy_type"] == "system_prompt"
    assert created["policy_name"] == "rag_turn"
    assert created["version"] == 1

    listed = admin_client.get(
        "/api/v1/admin/prompt-policies",
        headers=headers,
        params={"policy_type": "system_prompt"},
    )
    assert listed.status_code == 200
    policies = listed.json()["policies"]
    assert len(policies) == 1
    assert policies[0]["content"] == "Endpoint policy for {worker_id}."
    assert policies[0]["metadata"] == {"created_by_test": True}

    con = duckdb.connect(str(gateway_db), read_only=True)
    try:
        resolved = PromptPolicyResolver(db=con).format(
            "system_prompt",
            "rag_turn",
            worker_id="admin-worker",
        )
    finally:
        con.close()
    assert resolved == "Endpoint policy for admin-worker."

    deleted = admin_client.delete(
        "/api/v1/admin/prompt-policies/system_prompt/rag_turn",
        headers=headers,
        params={"version": 1},
    )
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True

    active = admin_client.get(
        "/api/v1/admin/prompt-policies",
        headers=headers,
        params={"policy_type": "system_prompt"},
    )
    assert active.status_code == 200
    assert active.json()["policies"] == []

    inactive = admin_client.get(
        "/api/v1/admin/prompt-policies",
        headers=headers,
        params={"policy_type": "system_prompt", "include_inactive": True},
    )
    assert inactive.status_code == 200
    assert inactive.json()["policies"][0]["status"] == "inactive"


def test_admin_sandbox_status(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from duckclaw.graphs import sandbox as sb

    monkeypatch.setattr(sb, "sandbox_runtime_status", lambda: {
        "docker_available": True,
        "publish_novnc": True,
        "public_url": "https://gw.example",
        "ttl_s": 600,
        "browser_image": "duckclaw/browser-env:latest",
        "compute_image": "duckclaw/sandbox:latest",
    })
    r = admin_client.get(
        "/api/v1/admin/sandbox/status",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ready"] is True
    assert data["docker_available"] is True


def test_admin_sandbox_chat_policy_deny_worker(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from routers import admin as admin_mod

    monkeypatch.setattr(
        admin_mod,
        "_playground_team_context",
        lambda **kwargs: {
            "authorized": True,
            "tenant_id": "default",
            "workers": ["default"],
            "telegram_user_id": "123",
            "team_chat_id": "123",
        },
    )
    monkeypatch.setattr(admin_mod, "_playground_vault_db_path", lambda _ctx, _wid: "/tmp/fake.duckdb")

    class _FakeDb:
        def close(self) -> None:
            pass

    monkeypatch.setattr(admin_mod, "_open_playground_vault_db", lambda _p, read_only=True: _FakeDb())
    monkeypatch.setattr(
        admin_mod,
        "_sandbox_chat_policy_payload",
        lambda **kwargs: {
            "chat_id": kwargs["chat_id"],
            "worker_id": "default",
            "sandbox_enabled": False,
            "sandbox_network_enabled": None,
            "yaml_network_default": "deny",
            "effective_network": "deny",
            "network_toggle_available": False,
            "browser_sandbox": False,
        },
    )

    r = admin_client.get(
        "/api/v1/admin/sandbox/chat-policy",
        headers={"X-Admin-Key": "test-admin-key"},
        params={"chat_id": "admin-section-vnc", "worker_id": "default"},
    )
    assert r.status_code == 200
    assert r.json()["network_toggle_available"] is False
    assert r.json()["effective_network"] == "deny"


def test_admin_sandbox_network_toggle(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from routers import admin as admin_mod

    monkeypatch.setattr(
        admin_mod,
        "_playground_team_context",
        lambda **kwargs: {
            "authorized": True,
            "tenant_id": "default",
            "workers": ["default"],
            "telegram_user_id": "123",
            "team_chat_id": "123",
        },
    )
    monkeypatch.setattr(admin_mod, "_playground_vault_db_path", lambda _ctx, _wid: "/tmp/fake.duckdb")

    class _FakeDb:
        def close(self) -> None:
            pass

    monkeypatch.setattr(admin_mod, "_open_playground_vault_db", lambda _p, read_only=True: _FakeDb())

    calls: list[tuple[str, str]] = []

    def _fake_set(db, chat_id, key, val, tenant_id="default"):
        calls.append((key, val))
        return True, ""

    def _fake_get(db, chat_id, key):
        return ""

    monkeypatch.setattr(
        "duckclaw.forge.schema.resolve_sandbox_network_policy",
        lambda _wid, _raw: (
            type("P", (), {"network": type("N", (), {"default": "allow"})()})(),
            {"toggle_available": True, "yaml_default": "allow", "effective": "allow"},
        ),
    )
    monkeypatch.setattr("duckclaw.graphs.on_the_fly_commands.set_chat_state_via_vault", _fake_set)
    monkeypatch.setattr("duckclaw.graphs.on_the_fly_commands.get_chat_state", _fake_get)
    monkeypatch.setattr(
        admin_mod,
        "_sandbox_chat_policy_payload",
        lambda **kwargs: {
            "chat_id": kwargs["chat_id"],
            "worker_id": "default",
            "effective_network": "allow",
            "network_toggle_available": True,
        },
    )
    monkeypatch.setattr(
        "duckclaw.graphs.sandbox.cleanup_sandbox_session_for_chat",
        lambda _cid: None,
    )

    r = admin_client.post(
        "/api/v1/admin/sandbox/network",
        headers={"X-Admin-Key": "test-admin-key"},
        json={"chat_id": "admin-section-vnc", "enabled": True, "worker_id": "default"},
    )
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert calls and calls[0] == ("sandbox_network_enabled", "true")


def test_admin_sandbox_novnc_prepare(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from duckclaw.graphs import sandbox as sb
    from routers import admin as admin_mod

    monkeypatch.setattr(admin_mod, "_worker_has_browser_sandbox", lambda _w: True)
    monkeypatch.setattr(
        sb,
        "sandbox_runtime_status",
        lambda: {"docker_available": True, "publish_novnc": True, "public_url": None, "ttl_s": 600},
    )
    monkeypatch.setattr(
        sb,
        "ensure_browser_novnc_session",
        lambda wid, sid, **_: f"http://127.0.0.1:6080/vnc.html?autoconnect=1&worker={wid}&sid={sid}",
    )

    def _touch(_sid: str) -> None:
        pass

    def _expires(_sid: str) -> float:
        import time

        return time.time() + 600

    from duckclaw.graphs import novnc_registry as nr

    monkeypatch.setattr(nr, "touch", _touch)
    monkeypatch.setattr(nr, "get_session_expires_at", _expires)

    r = admin_client.post(
        "/api/v1/admin/sandbox/novnc/prepare",
        headers={"X-Admin-Key": "test-admin-key"},
        json={"chat_id": "admin-playground", "worker_id": "default"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["vnc_url"]
    assert data["session_id"]
    assert data["worker_id"] == "default"


def test_admin_conversations_crud(admin_client: TestClient):
    from test_admin_conversations import build_fake_redis

    admin_client.app.state.redis = build_fake_redis()
    headers = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@duckclaw.local"}
    r = admin_client.post(
        "/api/v1/admin/conversations",
        headers=headers,
        params={"tenant_id": "default"},
        json={"title": "Test conv", "section": "playground", "worker_id": "default"},
    )
    assert r.status_code == 200
    data = r.json()
    sid = data.get("session_id")
    assert sid and sid.startswith("admin-conv-")

    r2 = admin_client.get(
        f"/api/v1/admin/conversations/{sid}",
        headers=headers,
        params={"tenant_id": "default"},
    )
    assert r2.status_code == 200
    assert r2.json().get("title") == "Test conv"

    r3 = admin_client.get(
        "/api/v1/admin/conversations",
        headers=headers,
        params={"tenant_id": "default", "section": "playground", "limit": 20},
    )
    assert r3.status_code == 200
    convs = r3.json().get("conversations") or []
    assert any(c.get("session_id") == sid for c in convs)

    r4 = admin_client.patch(
        f"/api/v1/admin/conversations/{sid}",
        headers=headers,
        params={"tenant_id": "default"},
        json={"title": "Renamed"},
    )
    assert r4.status_code == 200
    assert r4.json().get("title") == "Renamed"

    r5 = admin_client.delete(
        f"/api/v1/admin/conversations/{sid}",
        headers=headers,
        params={"tenant_id": "default"},
    )
    assert r5.status_code == 200
    assert r5.json().get("ok") is True
    assert r5.json().get("hard_deleted") is True

    r6 = admin_client.get(
        "/api/v1/admin/conversations",
        headers=headers,
        params={"tenant_id": "default", "section": "playground", "limit": 20},
    )
    assert r6.status_code == 200
    convs_after = r6.json().get("conversations") or []
    assert not any(c.get("session_id") == sid for c in convs_after)


def test_workspace_project_detail_endpoint(admin_client: TestClient):
    headers = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"}
    created = admin_client.post(
        "/api/v1/admin/workspace/projects",
        headers=headers,
        json={"name": "Detalle Proyecto", "description": "Proyecto DB-first"},
    )
    assert created.status_code == 200
    project_id = created.json()["project"]["project_id"]

    detail = admin_client.get(
        f"/api/v1/admin/workspace/projects/{project_id}",
        headers=headers,
    )
    assert detail.status_code == 200
    data = detail.json()
    assert data["project"]["project_id"] == project_id
    assert data["project"]["name"] == "Detalle Proyecto"
    assert data["agents"] == []


def test_gateway_db_fixture_applies_knowledge_migration(gateway_db: Path) -> None:
    import duckdb

    con = duckdb.connect(str(gateway_db), read_only=True)
    try:
        tables = {
            row[0]
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema='main'"
            ).fetchall()
        }
        versions = set()
        if "schema_migrations" in tables:
            versions = {
                int(row[0])
                for row in con.execute(
                    "SELECT version FROM main.schema_migrations ORDER BY version"
                ).fetchall()
            }
    finally:
        con.close()

    assert "schema_migrations" in tables
    assert "admin_knowledge_sources" in tables
    assert "admin_knowledge_documents" in tables
    assert "admin_knowledge_chunks" in tables
    assert 15 in versions


def test_knowledge_sources_and_search_are_scoped(
    gateway_admin_client: TestClient,
    gateway_db: Path,
) -> None:
    import duckdb

    from duckclaw.admin_user_profiles import tenant_id_for_email

    actor_email = "admin@test.local"
    tenant_id = tenant_id_for_email(actor_email)
    headers = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": actor_email}
    con = duckdb.connect(str(gateway_db))
    try:
        con.execute(
            """
            INSERT INTO main.admin_knowledge_sources
              (source_id, tenant_id, project_id, worker_uid, source_kind, source_uri, status)
            VALUES ('ksrc_api', ?, 'proj_api', 'wrk_api', 'folder', '/docs', 'ready')
            """,
            [tenant_id],
        )
        con.execute(
            """
            INSERT INTO main.admin_knowledge_documents
              (document_id, source_id, relative_path, title, checksum)
            VALUES ('kdoc_api', 'ksrc_api', 'aws/iam.md', 'IAM', 'sha256:api')
            """
        )
        con.execute(
            """
            INSERT INTO main.admin_knowledge_chunks
              (chunk_id, document_id, source_id, tenant_id, project_id, worker_uid,
               chunk_index, content, content_hash, embedding_status)
            VALUES
              ('kchk_api', 'kdoc_api', 'ksrc_api', ?, 'proj_api', 'wrk_api',
               0, 'Least privilege policies for cloud access', 'h-api', 'PENDING'),
              ('kchk_other', 'kdoc_api', 'ksrc_api', ?, 'proj_other', 'wrk_api',
               1, 'This other project must not leak', 'h-other', 'PENDING')
            """,
            [tenant_id, tenant_id],
        )
    finally:
        con.close()

    listed = gateway_admin_client.get(
        "/api/v1/admin/knowledge/sources",
        headers=headers,
        params={"project_id": "proj_api"},
    )
    assert listed.status_code == 200
    sources = listed.json()["sources"]
    assert len(sources) == 1
    assert sources[0]["source_id"] == "ksrc_api"
    assert sources[0]["chunk_count"] == 1

    searched = gateway_admin_client.post(
        "/api/v1/admin/knowledge/search",
        headers=headers,
        json={"query": "least privilege", "project_id": "proj_api", "worker_uid": "wrk_api"},
    )
    assert searched.status_code == 200
    results = searched.json()["results"]
    assert len(results) == 1
    assert results[0]["relative_path"] == "aws/iam.md"
    assert results[0]["match_type"] == "lexical"


def test_knowledge_uploads_create_project_scoped_chunks(
    gateway_admin_client: TestClient,
    gateway_db: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import duckdb

    monkeypatch.setenv("DUCKCLAW_SPAWN_PROFILE", "1")
    headers = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"}

    response = gateway_admin_client.post(
        "/api/v1/admin/knowledge/uploads",
        headers=headers,
        data={
            "project_id": "proj_upload",
            "worker_uid": "wrk_upload",
            "display_name": "AWS Docs",
        },
        files={
            "files": (
                "aws/iam.md",
                b"# IAM\n\nUse least privilege policies for cloud access.",
                "text/markdown",
            )
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["documents"] == 1
    assert payload["chunks"] >= 1

    con = duckdb.connect(str(gateway_db), read_only=True)
    try:
        row = con.execute(
            """
            SELECT s.project_id, s.worker_uid, d.relative_path, c.content
            FROM main.admin_knowledge_sources s
            JOIN main.admin_knowledge_documents d ON d.source_id = s.source_id
            JOIN main.admin_knowledge_chunks c ON c.source_id = s.source_id
            WHERE s.source_id = ?
            """,
            [payload["source_id"]],
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    assert row[0] == "proj_upload"
    assert row[1] == "wrk_upload"
    assert row[2] == "aws/iam.md"
    assert "least privilege" in row[3]


def test_admin_auth_login_smoke(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, session_redis
):
    from duckclaw.admin_console_users import ensure_admin_console_users_table, upsert_console_user

    from duckclaw.gateway_db import GATEWAY_DB_ENV_KEYS

    gw = tmp_path / "gw_access.duckdb"
    for key in GATEWAY_DB_ENV_KEYS:
        monkeypatch.setenv(key, str(gw))
    monkeypatch.setenv("DUCKCLAW_ADMIN_API_KEY", "test-admin-key")
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(Path(__file__).resolve().parent.parent))
    con = __import__("duckdb").connect(str(gw))
    try:
        class _A:
            def execute(self, sql: str, params=None):
                if params is not None:
                    return con.execute(sql, params)
                return con.execute(sql)

        adapter = _A()
        ensure_admin_console_users_table(adapter)
        upsert_console_user(
            adapter,
            email="smoke@test.local",
            nombre="Smoke",
            rol="admin",
            password="smokepass1",
        )
    finally:
        con.close()
    from gateway_import import load_gateway_app

    client = TestClient(load_gateway_app())
    client.app.state.redis = session_redis
    r = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "smoke@test.local", "password": "smokepass1"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["user"]["rol"] == "admin"
    assert data["user"]["email"] == "smoke@test.local"
    assert "session" in r.cookies


def test_playground_chat_images_smoke(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from core import vlm_ingest as vlm

    async def _fake_enrich(message: str, images):
        return f"{message}\nContexto visual adjunto: smoke"

    monkeypatch.setattr(vlm, "enrich_message_with_admin_images", _fake_enrich)
    monkeypatch.setenv("DUCKCLAW_OWNER_ID", "1")

    png_b64 = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    import main as gateway_main
    import routers.admin as admin_router

    async def _fake_invoke(*_a, **_k):
        return {"response": "ok"}

    monkeypatch.setattr(
        admin_router,
        "_playground_team_context",
        lambda **_: _mock_playground_team(workers=["default"]),
    )
    monkeypatch.setattr(gateway_main, "_invoke_chat", _fake_invoke)

    r = admin_client.post(
        "/api/v1/admin/playground/chat",
        headers={"X-Admin-Key": "test-admin-key"},
        json={
            "worker_id": "default",
            "message": "test",
            "images": [{"mime_type": "image/png", "data_base64": png_b64}],
        },
    )
    assert r.status_code == 200


def test_comfyui_templates(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/comfyui/templates",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "templates" in data
    assert isinstance(data["templates"], list)
    ids = {t["id"] for t in data["templates"]}
    assert "comfy_default" in ids


def test_comfyui_status_unreachable(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMFYUI_API_URL", "http://127.0.0.1:59999")
    r = admin_client.get(
        "/api/v1/admin/comfyui/status",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is False
    assert "error" in data
    assert data.get("source") in {"default", "env", "db"}
    assert data.get("runtime_key") == "comfyui.api_url"
    assert data.get("timeout_sec") == "300"
    assert data.get("timeout_source") in {"default", "env", "db"}


def test_comfyui_generate_mock(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COMFYUI_API_URL", "http://127.0.0.1:59998")
    monkeypatch.setenv("COMFYUI_TIMEOUT_SEC", "123")
    payload = {
        "ok": True,
        "file_path": "/tmp/fake.png",
        "prompt_id": "pid-1",
        "message": "ok",
    }
    seen: dict[str, object] = {}

    def _fake_impl(*_a, **kwargs):
        import json

        seen.update(kwargs.get("comfyui_config") or {})
        return json.dumps(payload)

    monkeypatch.setattr(
        "duckclaw.forge.skills.comfyui_bridge._generate_visual_asset_impl",
        _fake_impl,
    )

    r = admin_client.post(
        "/api/v1/admin/comfyui/generate",
        headers={"X-Admin-Key": "test-admin-key"},
        json={"prompt": "a red duck", "aspect_ratio": "1:1"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert data.get("file_path") == "/tmp/fake.png"
    assert seen.get("api_url") == "http://127.0.0.1:59998"
    assert seen.get("timeout_sec") == "123"


def test_comfyui_generate_bridge_error_400(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    def _fail(*_a, **_k):
        import json

        return json.dumps({"ok": False, "error": "No hay checkpoints en ComfyUI."})

    monkeypatch.setattr(
        "duckclaw.forge.skills.comfyui_bridge._generate_visual_asset_impl",
        _fail,
    )
    r = admin_client.post(
        "/api/v1/admin/comfyui/generate",
        headers={"X-Admin-Key": "test-admin-key"},
        json={"prompt": "test"},
    )
    assert r.status_code == 400
    body = r.json()
    detail = body.get("detail", body)
    msg = (
        detail.get("title", "")
        if isinstance(detail, dict)
        else str(detail)
    )
    assert "checkpoints" in str(msg).lower()


def test_ops_commands_include_comfyui(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/ops/commands",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    ids = {c["id"] for c in r.json().get("commands", [])}
    assert "pm2_start_comfyui" in ids
    assert "pm2_restart_comfyui" in ids
