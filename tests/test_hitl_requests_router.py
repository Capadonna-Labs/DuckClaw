"""The generic HITL act endpoint only forwards to the extension that owns the request; with none configured it refuses."""

from __future__ import annotations

from fastapi.testclient import TestClient

H = {"X-Admin-Key": "test-admin-key", "X-Duckclaw-Actor": "admin@test.local"}
BODY = {"kind": "signal", "id": "b29d3aef-1960-427d-8704-fe4d42db7f69", "action": "approve"}


def test_without_an_extension_provider_it_refuses(admin_client: TestClient, monkeypatch) -> None:
    monkeypatch.delenv("DUCKCLAW_HITL_ENTRYPOINT", raising=False)
    assert admin_client.post("/api/v1/admin/hitl/requests/act", headers=H, json=BODY).status_code == 503


def test_forwards_kind_id_action_note_and_actor(admin_client: TestClient, monkeypatch) -> None:
    from routers.admin_domains import hitl_requests

    seen: list[tuple] = []
    monkeypatch.setattr(hitl_requests, "_handler", lambda: lambda *a: seen.append(a) or {"ok": True, "message": "hecho"})
    r = admin_client.post("/api/v1/admin/hitl/requests/act", headers=H, json={**BODY, "action": "reject", "note": "no"})
    assert r.status_code == 200 and r.json() == {"ok": True, "message": "hecho"}
    assert seen == [("signal", BODY["id"], "reject", "no", "admin@test.local")]


def test_rejects_an_unknown_action_and_needs_the_admin_key(admin_client: TestClient) -> None:
    assert admin_client.post("/api/v1/admin/hitl/requests/act", headers=H, json={**BODY, "action": "execute"}).status_code == 422
    assert admin_client.post("/api/v1/admin/hitl/requests/act", json=BODY).status_code in (401, 403)


def test_a_successful_decision_sends_a_push_and_a_failed_one_does_not(admin_client: TestClient, monkeypatch) -> None:
    from routers.admin_domains import hitl_requests

    pushed: list[tuple] = []
    monkeypatch.setattr(hitl_requests, "_notify", lambda body, result: pushed.append((body.kind, body.action, result["message"])))
    outcome = {"ok": True, "message": "Señal cancelada"}
    monkeypatch.setattr(hitl_requests, "_handler", lambda: lambda *a: outcome)
    admin_client.post("/api/v1/admin/hitl/requests/act", headers=H, json={**BODY, "action": "reject"})
    outcome.update(ok=False)
    admin_client.post("/api/v1/admin/hitl/requests/act", headers=H, json=BODY)
    assert pushed == [("signal", "reject", "Señal cancelada")]
