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


def test_playground_config_team_for_telegram_chat(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from duckclaw import DuckClaw
    from duckclaw.workers.factory import list_workers

    all_w = list_workers()
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
    assert target in (data.get("workers") or [])
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


def test_playground_chat(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    gw_dir = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
    import sys

    if str(gw_dir) not in sys.path:
        sys.path.insert(0, str(gw_dir))
    import main as gateway_main
    import routers.admin as admin_router

    async def _fake_invoke(*_args, **_kwargs):
        return {"response": "respuesta-mock", "usage_tokens": {"total": 1}}

    monkeypatch.setattr(
        admin_router,
        "_playground_team_context",
        lambda **_: _mock_playground_team(workers=["AXIS-Maestro"]),
    )
    monkeypatch.setattr(gateway_main, "_invoke_chat", _fake_invoke)
    r = admin_client.post(
        "/api/v1/admin/playground/chat",
        headers={"X-Admin-Key": "test-admin-key"},
        json={"worker_id": "AXIS-Maestro", "message": "hola"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("ok") is True
    assert data.get("response") == "respuesta-mock"
    assert data.get("worker_id") == "AXIS-Maestro"


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
        lambda **_: _mock_playground_team(workers=["finanz"]),
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
    assert r2.status_code == 200
    assert r2.json().get("binding", {}).get("vault_id") == "custom"

    manifest_text = (worker_dir / "manifest.yaml").read_text(encoding="utf-8")
    assert "vault_binding" in manifest_text
    assert "custom" in manifest_text


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
    saved = env_file.read_text(encoding="utf-8")
    assert "other:tok_other:/api/v1/telegram/other:Worker-B:TenantB" in saved
    assert "mybot:tok1:/api/v1/telegram/mybot:Worker-A:TenantA" in saved


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
    monkeypatch.setenv("DUCKCLAW_GATEWAY_TENANT_ID", "Marco")
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
    assert data.get("effective_tenant_id") == "Marco"
    assert data.get("tenant_id") == "Marco"
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
    assert r2.json().get("tenant_id") == "Marco"

    con = duckdb.connect(str(dbf))
    row = con.execute(
        "SELECT tenant_id FROM main.authorized_users WHERE user_id = ?",
        [DEFAULT_TEST_TELEGRAM_USER_ID],
    ).fetchone()
    con.close()
    assert row is not None
    assert row[0] == "Marco"


def test_train_status_requires_key(admin_client: TestClient):
    assert admin_client.get("/api/v1/admin/train/status").status_code == 401


def test_train_status_ok(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/train/status",
        headers={"X-Admin-Key": "test-admin-key"},
    )
    assert r.status_code == 200
    data = r.json()
    assert "paths" in data
    assert "pipeline" in data


def test_train_sample_rejects_path_traversal(admin_client: TestClient):
    r = admin_client.get(
        "/api/v1/admin/train/traces/sample",
        headers={"X-Admin-Key": "test-admin-key"},
        params={"lake": "conversation_traces", "relative_path": "../../.env"},
    )
    assert r.status_code == 400


def test_train_collect(
    admin_client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    traces = tmp_path / "2026" / "05" / "17"
    traces.mkdir(parents=True)
    row = {
        "status": "SUCCESS",
        "messages": [
            {"role": "user", "content": "hola"},
            {"role": "assistant", "content": "ok"},
        ],
    }
    (traces / "traces.jsonl").write_text(
        json.dumps(row) + "\n", encoding="utf-8"
    )
    out = tmp_path / "dataset_sft.jsonl"
    monkeypatch.setenv("DUCKCLAW_CONVERSATION_TRACES_DIR", str(tmp_path))
    monkeypatch.setattr(
        "duckclaw.forge.sft.collector.DEFAULT_SFT_DATASET_PATH", out
    )
    r = admin_client.post(
        "/api/v1/admin/train/pipeline/collect",
        headers={"X-Admin-Key": "test-admin-key"},
        json={"require_valid_sql": False},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["records"] >= 1
    assert out.is_file()


def test_playground_team_hint_workers_label(admin_client: TestClient, monkeypatch: pytest.MonkeyPatch):
    from duckclaw import DuckClaw
    from duckclaw.workers.factory import list_workers

    all_w = list_workers()
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
        params={"workers": "finanz,default"},
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
                "worker_id": "finanz",
                "slot": 1,
                "chat_scope": None,
                "started_at": 1.0,
                "active": True,
            },
            {
                "worker_id": "finanz",
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
        params={"workers": "finanz"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["instances"]
    assert data["states"]["finanz:1"] == "en_progreso"
    assert data["states"]["finanz:2"] == "en_progreso"


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
            "workers": ["Quant-Trader"],
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
            "worker_id": "Quant-Trader",
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
        params={"chat_id": "admin-section-vnc", "worker_id": "Quant-Trader"},
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
            "workers": ["finanz"],
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
            "worker_id": "finanz",
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
        json={"chat_id": "admin-section-vnc", "enabled": True, "worker_id": "finanz"},
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
        json={"chat_id": "admin-playground", "worker_id": "finanz"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["vnc_url"]
    assert data["session_id"]
    assert data["worker_id"] == "finanz"


def test_admin_conversations_crud(admin_client: TestClient):
    from test_admin_conversations import build_fake_redis

    admin_client.app.state.redis = build_fake_redis()
    headers = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@duckclaw.local"}
    r = admin_client.post(
        "/api/v1/admin/conversations",
        headers=headers,
        params={"tenant_id": "default"},
        json={"title": "Test conv", "section": "playground", "worker_id": "finanz"},
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


def test_admin_auth_login_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    import sys

    from duckclaw.admin_console_users import ensure_admin_console_users_table, upsert_console_user

    from duckclaw.gateway_db import GATEWAY_DB_ENV_KEYS

    gw = tmp_path / "gw_access.duckdb"
    for key in GATEWAY_DB_ENV_KEYS:
        monkeypatch.setenv(key, str(gw))
    monkeypatch.setenv("DUCKCLAW_ADMIN_API_KEY", "test-admin-key")
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
            password="pw",
        )
    finally:
        con.close()
    repo = Path(__file__).resolve().parent.parent
    gw_dir = repo / "services" / "api-gateway"
    if str(gw_dir) not in sys.path:
        sys.path.insert(0, str(gw_dir))
    from main import app as gateway_app

    client = TestClient(gateway_app)
    r = client.post(
        "/api/v1/admin/auth/login",
        json={"email": "smoke@test.local", "password": "pw"},
    )
    assert r.status_code == 200
    assert r.json().get("rol") == "admin"


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
