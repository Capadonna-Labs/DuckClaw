"""Spawn package import sanitization."""

from __future__ import annotations

from duckclaw.spawn_package_import import import_spawn_package_to_catalog
from duckclaw.spawn_risk_policy import sanitize_manifest_for_import


def test_sanitize_manifest_for_import_read_only() -> None:
    manifest = {
        "id": "imp",
        "read_only": False,
        "tool_surface": {"expose_privileged_mutation_tools": ["admin_sql"]},
    }
    out = sanitize_manifest_for_import(manifest)
    assert out["read_only"] is True
    assert out["tool_surface"]["expose_privileged_mutation_tools"] == []


def test_import_spawn_package_to_catalog_creates_version(monkeypatch) -> None:
    import duckclaw.spawn_package_import as mod

    calls: list[str] = []

    def fake_add_version(db, **kwargs):
        calls.append(str(kwargs.get("change_note") or ""))

    monkeypatch.setattr(mod, "add_worker_version", fake_add_version)
    monkeypatch.setattr(
        mod,
        "ensure_profile_for_user",
        lambda db, email: {"email": email, "tenant_id": "default"},
    )
    monkeypatch.setattr(mod, "get_worker_by_tenant_worker_id", lambda db, **kw: None)
    monkeypatch.setattr(
        mod,
        "create_worker",
        lambda db, **kw: {"worker_uid": "wrk_test", "worker_id": kw["worker_id"]},
    )
    monkeypatch.setattr(mod, "list_worker_contexts", lambda db, **kw: [])
    monkeypatch.setattr(mod, "add_worker_context", lambda *a, **kw: None)
    monkeypatch.setattr(mod, "_context_files", lambda manifest, files: [])
    monkeypatch.setattr(mod, "sync_worker_system_prompt_policy", lambda *a, **kw: None)

    manifest = {"id": "imp", "skills": []}
    files = {"manifest.yaml": "id: imp\n", "system_prompt.md": "x"}
    result = import_spawn_package_to_catalog(None, owner_email="a@b.co", manifest=manifest, files=files)
    assert result["worker_id"] == "imp"
    assert calls
