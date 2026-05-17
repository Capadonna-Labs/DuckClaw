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
from duckops.sovereign.domain_labels import WizardStep, tailscale_funnel_wizard_panel_content
from duckops.sovereign.state_machine import (
    EXPRESS_STEP_ORDER,
    FULL_STEP_ORDER,
    next_step,
    next_step_in,
    prev_step,
    prev_step_in,
    step_order_for_profile,
)
from duckops.sovereign.tailscale_funnel import public_base_url_from_funnel_status
from duckops.sovereign.telegram_set_webhook import (
    _effective_telegram_bot_token,
    _effective_telegram_webhook_secret,
    build_set_webhook_body,
    webhook_full_url_for_draft,
)
from duckops.sovereign.duckdb_catalog import (
    build_neutral_duckdb_picker,
    discover_duckdb_files,
    find_axis_duckdb_in_repo,
    suggest_duckdb_vault_path,
)
from duckops.sovereign.duckdb_health import audit_duckdb, format_duckdb_health_rich, human_bytes
from duckops.sovereign.stack_health import audit_stack, format_stack_health_rich
from duckops.sovereign.ui import _express_apply_confirm
from duckops.sovereign.validate import private_db_dir_writable, suggest_gateway_port


def test_tailscale_funnel_panel_mentions_port_and_docs() -> None:
    text = tailscale_funnel_wizard_panel_content(8000)
    assert "8000" in text
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


def test_express_apply_confirm_accepts_enter() -> None:
    assert _express_apply_confirm("")
    assert _express_apply_confirm("CONFIRMAR")
    assert not _express_apply_confirm("no")


def test_fresh_draft_uses_neutral_defaults() -> None:
    from duckops.sovereign.wizard_reset import NEUTRAL_DUCKDB_VAULT, fresh_sovereign_draft

    d = fresh_sovereign_draft()
    assert d.duckdb_vault_path == NEUTRAL_DUCKDB_VAULT
    assert d.wizard_creator_telegram_user_id == ""


def test_build_neutral_duckdb_picker(tmp_path: Path) -> None:
    (tmp_path / "db").mkdir()
    (tmp_path / "db" / "a.duckdb").write_bytes(b"x")
    labels, values, _ = build_neutral_duckdb_picker(tmp_path)
    assert any("a.duckdb" in v for v in values)
    assert any("sovereign_memory" in v for v in values)
    assert "← sugerido" not in "\n".join(labels)


def test_find_axis_duckdb_in_repo() -> None:
    root = Path(__file__).resolve().parents[1]
    hit = find_axis_duckdb_in_repo(root)
    if hit:
        assert hit.endswith("axis.duckdb")


def test_suggest_duckdb_prefers_axis_over_siata(tmp_path: Path) -> None:
    db = tmp_path / "db" / "private" / "u"
    db.mkdir(parents=True)
    axis = db / "axis.duckdb"
    axis.write_bytes(b"")
    siata = tmp_path / "db" / "private" / "u" / "siatadb1.duckdb"
    siata.write_bytes(b"")
    d = SovereignDraft(duckdb_vault_path="db/private/u/siatadb1.duckdb")
    got = suggest_duckdb_vault_path(tmp_path, d)
    assert "axis" in got


def test_discover_duckdb_files(tmp_path: Path) -> None:
    p = tmp_path / "db" / "system.duckdb"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"x" * 10)
    picks = discover_duckdb_files(tmp_path)
    assert len(picks) == 1
    assert picks[0].rel_path == "db/system.duckdb"


def test_human_bytes() -> None:
    assert human_bytes(0) == "0 B"
    assert "KB" in human_bytes(2048) or "2.0 KB" in human_bytes(2048)


def test_audit_duckdb_missing_file(tmp_path: Path) -> None:
    d = SovereignDraft(duckdb_vault_path="db/test_vault.duckdb")
    health = audit_duckdb(tmp_path, d, quick=True)
    assert not health.exists
    assert health.ok
    text = format_duckdb_health_rich(health)
    assert "se creará" in text


def test_audit_stack_includes_duckdb_and_interop(tmp_path: Path) -> None:
    d = SovereignDraft(redis_url="redis://127.0.0.1:9")
    report = audit_stack(tmp_path, d)
    labels = [c.label for c in report.checks]
    assert labels == ["Redis", "DuckDB", "Gateway", "DB-Writer", "Interoperabilidad"]
    duck = audit_duckdb(tmp_path, d)
    text = format_stack_health_rich(report, duck_block=format_duckdb_health_rich(duck))
    assert "Estado general" in text
    assert "duckclaw-admin" in text


def test_express_order_stack_then_review() -> None:
    assert step_order_for_profile("express") == EXPRESS_STEP_ORDER
    assert step_order_for_profile("full") == FULL_STEP_ORDER
    assert WizardStep.CONNECTIVITY not in EXPRESS_STEP_ORDER
    assert next_step_in(EXPRESS_STEP_ORDER, WizardStep.SOVEREIGNTY_AUDIT) == WizardStep.CORE_SERVICES
    assert next_step_in(EXPRESS_STEP_ORDER, WizardStep.CORE_SERVICES) == WizardStep.ORCHESTRATION
    assert next_step_in(EXPRESS_STEP_ORDER, WizardStep.ORCHESTRATION) == WizardStep.REVIEW_DEPLOY
    assert next_step_in(EXPRESS_STEP_ORDER, WizardStep.REVIEW_DEPLOY) is None


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
    assert "TELEGRAM_JOB_HUNTER_TOKEN" not in env
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
    assert "TELEGRAM_JOB_HUNTER_TOKEN" not in env
    assert "DUCKCLAW_DEFAULT_WORKER_ID" not in env
    assert env["DUCKDB_PATH"] == str((root / "db/private/jh.duckdb").resolve())


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


def test_duck_mascot_frames_and_states() -> None:
    from duckops.sovereign.duck_mascot import (
        DuckMascot,
        FRAMES_BY_STATE,
        MascotState,
        _SPINNERS,
    )

    assert len(FRAMES_BY_STATE[MascotState.IDLE]) >= 2
    duck = DuckMascot(state=MascotState.WORKING)
    text = duck.render_rich()
    plain = str(text)
    assert "claw" in plain.lower()
    assert duck._current_spinner in _SPINNERS
    before = duck._current_spinner
    duck.tick()
    assert duck._current_spinner != before or len(_SPINNERS) == 1
    duck.set_state(MascotState.WALKING)
    assert duck.current_lines()


def test_duck_mascot_inertia_moves_toward_target(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckops.sovereign import duck_mascot
    from duckops.sovereign.duck_mascot import DuckMascot, MascotState

    # Sin re-target aleatorio al llegar (15% en update_logic) — el test fija destino explícito.
    monkeypatch.setattr(duck_mascot.random, "random", lambda: 1.0)

    duck = DuckMascot(x=0, y=0)
    duck.target_x, duck.target_y = 3, 2
    duck.state = MascotState.WALKING
    for _ in range(10):
        duck.update_logic(10, 10)
    assert duck.x == 3 and duck.y == 2


def test_mascot_art_compat_string() -> None:
    from duckops.sovereign.tui_shell import MASCOT_ART

    assert "claw" in MASCOT_ART.lower()


def test_status_log_renders_done_and_active() -> None:
    from duckops.sovereign.tui_shell import StatusLog, StepStatus

    log = StatusLog()
    log.pending("Tu equipo")
    log.active("Datos y cola")
    log.complete("Tu equipo")
    text = log.render()
    assert "Tu equipo" in text
    assert "Datos y cola" in text
    assert "●" in text
    log.set_step("Datos y cola", StepStatus.DONE)
    assert "Datos y cola" in log.render()


def test_render_header_includes_version_and_repo(tmp_path: Path) -> None:
    from rich.console import Console

    from duckops.sovereign.draft import SovereignDraft
    from duckops.sovereign.tui_shell import StepInfo, render_header

    draft = SovereignDraft(tenant_id="TestTenant", default_worker_id="AXIS-Maestro")
    panel_wizard = render_header(
        draft,
        tmp_path,
        StepInfo(profile_label="Prueba"),
    )
    panel_chat = render_header(
        draft,
        tmp_path,
        StepInfo(profile_label="Chat"),
        show_tenant=True,
    )
    console = Console(width=120, record=True)
    console.print(panel_wizard)
    wizard_text = console.export_text()
    assert "DuckClaw" in wizard_text
    assert "TestTenant" not in wizard_text
    assert "DuckDB" in wizard_text
    console = Console(width=120, record=True)
    console.print(panel_chat)
    chat_text = console.export_text()
    assert "TestTenant" in chat_text
    assert "claw" in chat_text.lower() or "▄" in chat_text


def test_playground_chat_client_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckops.sovereign.tui_chat import GatewayChatConfig, PlaygroundChatClient

    cfg = GatewayChatConfig(
        base_url="http://127.0.0.1:9999",
        admin_key="secret",
        tenant_id="default",
        telegram_user_id="1",
        default_worker_id="default",
    )
    client = PlaygroundChatClient(cfg)

    async def _fake_post(*_a: object, **_k: object) -> dict:
        return {"ok": True, "response": "hola-mock", "worker_id": "default"}

    monkeypatch.setattr(client, "_post_chat_async", _fake_post)
    out = client.post_chat("ping")
    assert out.get("response") == "hola-mock"


def test_load_gateway_chat_config_from_env(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from duckops.sovereign.tui_chat import load_gateway_chat_config

    monkeypatch.delenv("DUCKCLAW_ADMIN_API_KEY", raising=False)
    monkeypatch.delenv("DUCKCLAW_GATEWAY_URL", raising=False)
    monkeypatch.delenv("DUCKCLAW_OWNER_ID", raising=False)
    import duckops.sovereign.tui_chat as tui_chat

    monkeypatch.setattr(tui_chat, "load_draft_json", lambda: None)
    (tmp_path / ".env").write_text(
        "DUCKCLAW_GATEWAY_URL=http://127.0.0.1:8484\n"
        "DUCKCLAW_ADMIN_API_KEY=adm\n"
        "DUCKCLAW_DEFAULT_WORKER_ID=finanz\n"
        "DUCKCLAW_OWNER_ID=42\n",
        encoding="utf-8",
    )
    cfg = load_gateway_chat_config(tmp_path)
    assert cfg.base_url == "http://127.0.0.1:8484"
    assert cfg.admin_key == "adm"
    assert cfg.default_worker_id == "finanz"
    assert cfg.telegram_user_id == "42"


def test_workers_catalog_lists_forge_templates() -> None:
    from duckops.sovereign.workers_catalog import (
        list_worker_picks,
        resolve_worker_choice,
        suggest_default_worker_id,
    )

    repo = Path(__file__).resolve().parent.parent
    picks = list_worker_picks(repo)
    ids = {p.worker_id for p in picks}
    assert "AXIS-Maestro" in ids
    assert "default" in ids
    assert resolve_worker_choice("1", picks, repo) == picks[0].worker_id
    assert resolve_worker_choice("maestro", picks, repo) == "AXIS-Maestro"
    assert suggest_default_worker_id(picks, "nope") in ids


def test_materialize_writes_owner_and_team_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from duckops.sovereign import materialize as m

    root = tmp_path / "repo"
    root.mkdir()
    (root / ".env").write_text("EXISTING=1\n", encoding="utf-8")
    (root / "config").mkdir()
    d = SovereignDraft(
        wizard_creator_telegram_user_id="123456789",
        gateway_team_templates="finanz, BI-Analyst",
        default_worker_id="finanz",
        redis_url="redis://localhost:6379/0",
        duckdb_vault_path="db/test.duckdb",
        tenant_id="Marco",
    )
    monkeypatch.setattr(m, "ensure_duckdb_file", lambda *_a, **_k: True)
    monkeypatch.setattr(m, "seed_telegram_guard_admins", lambda *_a, **_k: None)
    monkeypatch.setattr(m, "patch_security_policy", lambda *_a, **_k: None)
    monkeypatch.setattr(m, "patch_api_gateways_pm2_for_draft", lambda *_a, **_k: None)
    monkeypatch.setattr(m, "register_telegram_webhook_after_deploy", lambda *_a, **_k: None)
    monkeypatch.setattr(m, "_print_post_wizard_next_steps", lambda *_a, **_k: None)
    monkeypatch.setattr(m, "save_wizard_config_json", lambda _draft: None)

    rc = m.materialize(root, d, console_print=lambda _msg: None, deploy_pm2=False)
    assert rc == 0
    text = (root / ".env").read_text(encoding="utf-8")
    assert "DUCKCLAW_OWNER_ID=123456789" in text
    assert "DUCKCLAW_GATEWAY_TEAM_TEMPLATES=finanz, BI-Analyst" in text
