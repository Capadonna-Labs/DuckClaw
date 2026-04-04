"""Tests Sovereign Wizard v2.0 (sin TUI)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from duckops.sovereign.atomic import atomic_write
from duckops.sovereign.draft import SovereignDraft
from duckops.sovereign.materialize import (
    effective_primary_duckdb_relpath,
    merge_env_file,
    patch_api_gateways_pm2_for_draft,
    shared_attach_relpath,
    telegram_webhook_post_deploy_message,
)
from duckops.sovereign.domain_labels import tailscale_funnel_wizard_panel_content
from duckops.sovereign.state_machine import WizardStep, next_step, prev_step
from duckops.sovereign.tailscale_funnel import public_base_url_from_funnel_status
from duckops.sovereign.telegram_set_webhook import (
    _effective_telegram_bot_token,
    _effective_telegram_webhook_secret,
    build_set_webhook_body,
    webhook_full_url_for_draft,
)
from duckops.sovereign.validate import private_db_dir_writable, suggest_gateway_port


def test_tailscale_funnel_panel_mentions_port_and_docs() -> None:
    text = tailscale_funnel_wizard_panel_content(8000)
    assert "tailscale funnel --bg --yes 8000" in text
    assert "tailscale.com/kb/1223/funnel" in text


def test_telegram_webhook_post_deploy_message_uses_public_base() -> None:
    d = SovereignDraft(
        gateway_port=8000,
        gateway_pm2_name="Finanz-Gateway",
        telegram_webhook_public_base_url="https://finanz.example.test",
    )
    msg = telegram_webhook_post_deploy_message(d)
    assert "https://finanz.example.test/api/v1/telegram/webhook" in msg
    assert "Finanz-Gateway" in msg
    assert "8000" in msg


def test_telegram_webhook_post_deploy_mentions_cloudflared_pm2_name() -> None:
    d = SovereignDraft(
        gateway_port=8282,
        gateway_pm2_name="G",
        telegram_webhook_public_base_url="https://abc.trycloudflare.com",
        cloudflared_pm2_process_name="G-cloudflared",
    )
    msg = telegram_webhook_post_deploy_message(d)
    assert "G-cloudflared" in msg
    assert "pm2 list" in msg.lower()


def test_telegram_webhook_post_deploy_funnel_hint_for_ts_net() -> None:
    d = SovereignDraft(
        gateway_port=8282,
        telegram_webhook_public_base_url="https://machine.example.ts.net",
    )
    msg = telegram_webhook_post_deploy_message(d)
    assert "tailscale funnel status" in msg


def test_telegram_webhook_post_deploy_funnel_hint_via_wizard_flag() -> None:
    d = SovereignDraft(gateway_port=8282, tailscale_funnel_bg_via_wizard=True)
    msg = telegram_webhook_post_deploy_message(d)
    assert "Funnel/Tailscale" in msg


def test_public_base_url_from_funnel_status_requires_proxy_port() -> None:
    data = {
        "Web": {
            "machine.example.ts.net:443": {
                "Handlers": {"/": {"Proxy": "http://127.0.0.1:8282"}},
            }
        },
        "AllowFunnel": {"machine.example.ts.net:443": True},
    }
    assert (
        public_base_url_from_funnel_status(data, expected_local_port=8282)
        == "https://machine.example.ts.net"
    )
    assert public_base_url_from_funnel_status(data, expected_local_port=9999) is None


def test_webhook_full_url_for_draft() -> None:
    d = SovereignDraft(telegram_webhook_public_base_url="https://node.example.ts.net")
    assert (
        webhook_full_url_for_draft(d)
        == "https://node.example.ts.net/api/v1/telegram/webhook"
    )


def test_webhook_full_url_skips_placeholder() -> None:
    d = SovereignDraft(
        telegram_webhook_public_base_url="https://TU_TUNEL_A_PUERTO_8282/api/v1/telegram/webhook"
    )
    assert webhook_full_url_for_draft(d) is None


def test_build_set_webhook_body_includes_secret_when_set(tmp_path: Path) -> None:
    d = SovereignDraft(
        telegram_webhook_public_base_url="https://h.example",
        telegram_webhook_secret="s3cr3t",
    )
    body = build_set_webhook_body(tmp_path, d)
    assert body is not None
    assert body["secret_token"] == "s3cr3t"
    assert body["url"] == "https://h.example/api/v1/telegram/webhook"
    assert body["allowed_updates"] == ["message", "edited_message"]


def test_build_set_webhook_body_omits_secret_when_empty(tmp_path: Path) -> None:
    d = SovereignDraft(telegram_webhook_public_base_url="https://h.example")
    body = build_set_webhook_body(tmp_path, d)
    assert body is not None
    assert "secret_token" not in body


def test_build_set_webhook_body_reads_secret_from_env_when_draft_empty(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "TELEGRAM_WEBHOOK_SECRET=fromenv\n", encoding="utf-8"
    )
    d = SovereignDraft(telegram_webhook_public_base_url="https://h.example")
    body = build_set_webhook_body(tmp_path, d)
    assert body is not None
    assert body["secret_token"] == "fromenv"


def test_build_set_webhook_draft_secret_overrides_env(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "TELEGRAM_WEBHOOK_SECRET=fromenv\n", encoding="utf-8"
    )
    d = SovereignDraft(
        telegram_webhook_public_base_url="https://h.example",
        telegram_webhook_secret="fromdraft",
    )
    body = build_set_webhook_body(tmp_path, d)
    assert body is not None
    assert body["secret_token"] == "fromdraft"


def test_public_base_url_from_funnel_status_requires_allow() -> None:
    data = {
        "Web": {
            "machine.example.ts.net:443": {
                "Handlers": {"/": {"Proxy": "http://127.0.0.1:8282"}},
            }
        },
        "AllowFunnel": {},
    }
    assert public_base_url_from_funnel_status(data, expected_local_port=8282) is None


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


def test_merge_env_file_respects_immutable_sentinel(tmp_path: Path) -> None:
    (tmp_path / ".env.immutable").write_text("", encoding="utf-8")
    (tmp_path / ".env").write_text("EXISTING=1\n", encoding="utf-8")
    assert merge_env_file(tmp_path, {"X": "y"}) is False
    assert "EXISTING=1" in (tmp_path / ".env").read_text(encoding="utf-8")
    prop = tmp_path / "config" / "dotenv_wizard_proposed.env"
    assert prop.is_file()
    body = prop.read_text(encoding="utf-8")
    assert "X=y" in body


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
                "env": {"DUCKDB_PATH": "/old/abs.duckdb"},
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
    dbp = out["apps"][0]["env"]["DUCKDB_PATH"]
    assert str((root / "db/private/x/bi_analyst.duckdb").resolve()) == dbp
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
                    "DUCKDB_PATH": "/_prior.duckdb",
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
    assert env["DUCKDB_PATH"] == str((root / "db/new_vault.duckdb").resolve())


def test_patch_api_gateways_pm2_merges_telegram_env_updates(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    cfg = {
        "apps": [
            {
                "name": "JobHunter-Gateway",
                "env": {
                    "DUCKDB_PATH": "/old.duckdb",
                    "TELEGRAM_JOB_HUNTER_TOKEN": "stale_token",
                },
            }
        ]
    }
    (root / "config" / "api_gateways_pm2.json").write_text(
        json.dumps(cfg, indent=2), encoding="utf-8"
    )
    draft = SovereignDraft(
        gateway_pm2_name="JobHunter-Gateway",
        duckdb_shared_path="db/private/jh.duckdb",
        default_worker_id="Job-Hunter",
    )
    patch_api_gateways_pm2_for_draft(
        root,
        draft,
        lambda _m: None,
        env_updates={"TELEGRAM_JOB_HUNTER_TOKEN": "fresh_token", "DUCKCLAW_TELEGRAM_MCP_ENABLED": "1"},
    )
    out = json.loads((root / "config" / "api_gateways_pm2.json").read_text(encoding="utf-8"))
    env = out["apps"][0]["env"]
    assert env["TELEGRAM_JOB_HUNTER_TOKEN"] == "fresh_token"
    assert env["DUCKCLAW_TELEGRAM_MCP_ENABLED"] == "1"
    assert env["DUCKDB_PATH"] == str((root / "db/private/jh.duckdb").resolve())


def test_patch_api_gateways_pm2_new_app_includes_proposed_telegram(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / "config" / "dotenv_wizard_proposed.env").write_text(
        "TELEGRAM_JOB_HUNTER_TOKEN=token_from_proposed\n",
        encoding="utf-8",
    )
    (root / "config" / "api_gateways_pm2.json").write_text(
        json.dumps({"apps": []}, indent=2), encoding="utf-8"
    )
    draft = SovereignDraft(
        gateway_pm2_name="JobHunter-Gateway",
        gateway_port=8484,
        duckdb_shared_path="db/private/jh.duckdb",
        default_worker_id="Job-Hunter",
        redis_url="redis://localhost:6379/1",
    )
    patch_api_gateways_pm2_for_draft(
        root,
        draft,
        lambda _m: None,
        env_updates={"DUCKCLAW_DEFAULT_WORKER_ID": "Job-Hunter"},
    )
    out = json.loads((root / "config" / "api_gateways_pm2.json").read_text(encoding="utf-8"))
    assert len(out["apps"]) == 1
    env = out["apps"][0]["env"]
    assert env["TELEGRAM_JOB_HUNTER_TOKEN"] == "token_from_proposed"
    assert env["DUCKCLAW_DEFAULT_WORKER_ID"] == "Job-Hunter"


def test_effective_telegram_reads_proposed_when_root_env_empty(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / ".env").write_text("# minimal\n", encoding="utf-8")
    (root / "config" / "dotenv_wizard_proposed.env").write_text(
        "TELEGRAM_JOB_HUNTER_TOKEN=secret_from_proposed\n"
        "TELEGRAM_WEBHOOK_SECRET=whsec_proposed\n",
        encoding="utf-8",
    )
    d = SovereignDraft(
        telegram_bot_token="",
        telegram_webhook_secret="",
        default_worker_id="Job-Hunter",
    )
    assert _effective_telegram_bot_token(root, d) == "secret_from_proposed"
    assert _effective_telegram_webhook_secret(root, d) == "whsec_proposed"


def test_draft_json_roundtrip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from duckops.sovereign import materialize as m

    cfg = tmp_path / "duckclaw"
    cfg.mkdir()
    monkeypatch.setattr(m, "_wizard_config_path", lambda: cfg / "wizard_config.json")
    d = SovereignDraft(redis_url="redis://x:9/0", tenant_id="t1")
    m.save_wizard_config_json(d)
    assert (cfg / "wizard_config.json").is_file()


def test_wizard_config_default_worker_id_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from duckops.sovereign import materialize as m

    cfg = tmp_path / "duckclaw"
    cfg.mkdir()
    monkeypatch.setattr(m, "_wizard_config_path", lambda: cfg / "wizard_config.json")
    d = SovereignDraft(default_worker_id="Job-Hunter")
    m.save_wizard_config_json(d)
    data = json.loads((cfg / "wizard_config.json").read_text(encoding="utf-8"))
    assert data.get("default_worker_id") == "Job-Hunter"
    assert m.load_last_default_worker_id_from_wizard_config() == "Job-Hunter"


def test_wizard_config_gateway_port_roundtrip(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from duckops.sovereign import materialize as m

    cfg = tmp_path / "duckclaw"
    cfg.mkdir()
    monkeypatch.setattr(m, "_wizard_config_path", lambda: cfg / "wizard_config.json")
    d = SovereignDraft(gateway_port=8484)
    m.save_wizard_config_json(d)
    data = json.loads((cfg / "wizard_config.json").read_text(encoding="utf-8"))
    assert data.get("gateway_port") == 8484
    assert m.load_last_gateway_port_from_wizard_config() == 8484


def test_gateway_port_hint_from_api_gateways_json(tmp_path: Path) -> None:
    from duckops.sovereign import materialize as m

    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    cfg = {"apps": [{"name": "JobHunter-Gateway", "port": 8484, "env": {}}]}
    (root / "config" / "api_gateways_pm2.json").write_text(
        json.dumps(cfg, indent=2), encoding="utf-8"
    )
    assert m.load_gateway_port_hint_from_api_gateways_json(root, "JobHunter-Gateway") == 8484
    assert m.load_gateway_port_hint_from_api_gateways_json(root, "Missing-Gateway") is None


def test_default_worker_id_hint_from_repo_env(tmp_path: Path) -> None:
    from duckops.sovereign import materialize as m

    root = tmp_path / "repo"
    root.mkdir()
    (root / ".env").write_text("DUCKCLAW_DEFAULT_WORKER_ID=finanz\n", encoding="utf-8")
    assert m.load_default_worker_id_hint_from_repo_env(root) == "finanz"
