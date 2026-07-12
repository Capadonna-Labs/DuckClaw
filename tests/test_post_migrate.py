from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

from duckops.post_migrate import run_post_migrate_housekeeping


def test_post_migrate_applies_framework_and_sync(tmp_path: Path, monkeypatch) -> None:
    hub = tmp_path / "hub.duckdb"
    hub.write_bytes(b"")
    calls: list[str] = []

    monkeypatch.setattr(
        "duckclaw.gateway_db.get_gateway_db_path",
        lambda: str(hub),
    )
    monkeypatch.setattr(
        "duckops.policy_health.check_framework_prompt_policies",
        lambda _db: type("H", (), {"ok": True, "degraded": True})(),
    )
    monkeypatch.setattr(
        "duckops.policy_health.check_catalog_worker_system_prompts",
        lambda _db: type("H", (), {"ok": False, "missing_worker_ids": ("a",)})(),
    )
    monkeypatch.setattr(
        "duckclaw.framework_policy_pack.apply_framework_policy_pack",
        lambda _db: calls.append("framework") or ["capability/default_fallback"],
    )
    monkeypatch.setattr(
        "duckclaw.catalog_prompt_sync.sync_all_catalog_worker_prompts",
        lambda _db, **kwargs: calls.append("sync") or {"synced": ["a"], "skipped": [], "failed": []},
    )

    import duckdb

    real_connect = duckdb.connect

    def _connect(path: str, read_only: bool = False):
        if str(path) == str(hub):
            mock = MagicMock()
            mock.__enter__ = lambda self: self
            mock.__exit__ = lambda *a: None
            return mock
        return real_connect(path, read_only=read_only)

    monkeypatch.setattr("duckdb.connect", _connect)
    (tmp_path / ".env").write_text("DUCKCLAW_ADMIN_EMAIL=dev@test.local\n", encoding="utf-8")

    lines: list[str] = []
    run_post_migrate_housekeeping(tmp_path, lines.append)

    assert "framework" in calls
    assert "sync" in calls
    assert any("post-migrate" in line for line in lines)
