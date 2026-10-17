"""A2A discovery and spawn import go through the DB-Writer (gateway stays read-only)."""

import pytest

from duckclaw.write_handlers import workers


def test_set_a2a_discoverable_handler(monkeypatch):
    calls = {}
    monkeypatch.setattr(workers, "get_worker_by_tenant_worker_id", lambda conn, tenant_id, worker_id: {"worker_uid": "wrk_1"} if worker_id == "w" else None)
    monkeypatch.setattr(workers, "set_worker_a2a_discoverable", lambda conn, worker_uid, discoverable: calls.update(uid=worker_uid, on=discoverable))
    workers._apply_set_worker_a2a_discoverable(None, {"tenant_id": "t", "worker_id": "w", "discoverable": True})
    assert calls == {"uid": "wrk_1", "on": True}
    with pytest.raises(ValueError):
        workers._apply_set_worker_a2a_discoverable(None, {"tenant_id": "t", "worker_id": "missing", "discoverable": True})


def test_import_spawn_package_handler_forces_read_only(monkeypatch):
    import duckclaw.spawn_package_import as spi

    seen = {}
    monkeypatch.setattr(workers, "ensure_profile_for_user", lambda conn, email: {"email": email})
    monkeypatch.setattr(spi, "import_spawn_package_to_catalog", lambda conn, **kw: seen.update(kw) or {"worker_id": "x"})
    workers._apply_import_spawn_package(None, {"actor_email": "a@b.co", "manifest": {"id": "x"}, "files": {"system_prompt.md": "hi"}})
    assert seen["owner_email"] == "a@b.co" and seen["force_read_only"] is True and seen["worker_id_override"] is None
