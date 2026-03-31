"""Tests Sovereign Wizard v2.0 (sin TUI)."""

from __future__ import annotations

from pathlib import Path

import pytest

from duckops.sovereign.atomic import atomic_write
from duckops.sovereign.draft import SovereignDraft
from duckops.sovereign.materialize import (
    effective_primary_duckdb_relpath,
    merge_env_file,
    patch_api_gateways_pm2_for_draft,
    shared_attach_relpath,
)
from duckops.sovereign.state_machine import WizardStep, next_step, prev_step
from duckops.sovereign.validate import private_db_dir_writable, suggest_gateway_port


def test_state_machine_navigation() -> None:
    assert next_step(WizardStep.SOVEREIGNTY_AUDIT) == WizardStep.CORE_SERVICES
    assert prev_step(WizardStep.CORE_SERVICES) == WizardStep.SOVEREIGNTY_AUDIT
    assert prev_step(WizardStep.SOVEREIGNTY_AUDIT) is None
    assert next_step(WizardStep.REVIEW_DEPLOY) is None


def test_atomic_write_backup_and_restore(tmp_path: Path) -> None:
    p = tmp_path / "f.txt"
    p.write_text("old", encoding="utf-8")
    atomic_write(p, "new")
    assert p.read_text() == "new\n" or p.read_text() == "new"
    # backup exists
    assert (tmp_path / "f.txt.bak").is_file() or p.with_suffix(p.suffix + ".bak").is_file()


def test_merge_env_file_creates_and_merges(tmp_path: Path) -> None:
    merge_env_file(tmp_path, {"A": "1", "B": "2"})
    t = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "A=1" in t and "B=2" in t
    merge_env_file(tmp_path, {"A": "9"})
    t2 = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "A=9" in t2
    assert "B=2" in t2


def test_suggest_gateway_port_free(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import duckops.sovereign.validate as v

    def _never_used(*_a: object, **_k: object) -> bool:
        return False

    monkeypatch.setattr(v, "is_port_in_use", _never_used)
    assert suggest_gateway_port("127.0.0.1", 8282) == 8282


def test_private_db_dir_writable_tmp(tmp_path: Path) -> None:
    assert private_db_dir_writable(tmp_path) is True


def test_effective_primary_uses_shared_when_vault_is_default() -> None:
    d = SovereignDraft(duckdb_shared_path="db/private/u/bi_analyst.duckdb")
    assert effective_primary_duckdb_relpath(d) == "db/private/u/bi_analyst.duckdb"
    assert shared_attach_relpath(d) is None


def test_effective_primary_dual_vault_and_shared() -> None:
    d = SovereignDraft(
        duckdb_vault_path="db/private/a/vault.duckdb",
        duckdb_shared_path="db/shared/catalog.duckdb",
    )
    assert effective_primary_duckdb_relpath(d) == "db/private/a/vault.duckdb"
    assert shared_attach_relpath(d) == "db/shared/catalog.duckdb"


def test_patch_api_gateways_pm2_json_updates_db_path(tmp_path: Path) -> None:
    import json

    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    cfg = {
        "apps": [
            {
                "name": "BI-Analyst-Gateway",
                "port": 8282,
                "env": {"DUCKCLAW_DB_PATH": "/old/abs.duckdb"},
            }
        ]
    }
    (root / "config" / "api_gateways_pm2.json").write_text(
        json.dumps(cfg, indent=2), encoding="utf-8"
    )
    draft = SovereignDraft(
        gateway_pm2_name="BI-Analyst-Gateway",
        duckdb_shared_path="db/private/x/bi_analyst.duckdb",
    )
    msgs: list[str] = []
    patch_api_gateways_pm2_for_draft(root, draft, msgs.append)
    out = json.loads((root / "config" / "api_gateways_pm2.json").read_text(encoding="utf-8"))
    dbp = out["apps"][0]["env"]["DUCKCLAW_DB_PATH"]
    assert str(root / "db/private/x/bi_analyst.duckdb") == dbp
    assert "DUCKCLAW_SHARED_DB_PATH" not in out["apps"][0]["env"]


def test_patch_pm2_preserves_shared_when_draft_has_no_secondary(tmp_path: Path) -> None:
    import json

    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    shared_path = str(tmp_path / "shared.duckdb")
    cfg = {
        "apps": [
            {
                "name": "Leila-Gateway",
                "env": {
                    "DUCKCLAW_DB_PATH": "/_prior.duckdb",
                    "DUCKCLAW_SHARED_DB_PATH": shared_path,
                },
            }
        ]
    }
    (root / "config" / "api_gateways_pm2.json").write_text(
        json.dumps(cfg, indent=2), encoding="utf-8"
    )
    draft = SovereignDraft(
        gateway_pm2_name="Leila-Gateway",
        duckdb_vault_path="db/new_vault.duckdb",
        duckdb_shared_path="",
    )
    patch_api_gateways_pm2_for_draft(root, draft, lambda _m: None)
    out = json.loads((root / "config" / "api_gateways_pm2.json").read_text(encoding="utf-8"))
    env = out["apps"][0]["env"]
    assert env["DUCKCLAW_SHARED_DB_PATH"] == shared_path
    assert env["DUCKCLAW_DB_PATH"] == str((root / "db/new_vault.duckdb").resolve())


def test_draft_json_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from duckops.sovereign import materialize as m

    cfg = tmp_path / "duckclaw"
    cfg.mkdir()
    monkeypatch.setattr(m, "_wizard_config_path", lambda: cfg / "wizard_config.json")
    d = SovereignDraft(redis_url="redis://x:9/0", tenant_id="t1")
    m.save_wizard_config_json(d)
    assert (cfg / "wizard_config.json").is_file()
