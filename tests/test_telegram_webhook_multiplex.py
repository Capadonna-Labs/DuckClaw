"""Enrutamiento multi-bot por cabecera secret_token (DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from duckclaw.integrations.telegram import telegram_webhook_multiplex as m


@pytest.fixture(autouse=True)
def _clear_route_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    m._cached_bindings = None
    m._cached_bindings_error = None
    monkeypatch.delenv("DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES", raising=False)
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)


def test_classic_no_secret_allows_any_header(monkeypatch: pytest.MonkeyPatch) -> None:
    r = m.telegram_webhook_resolve_dispatch(
        "anything",
        default_worker_id="platform-orchestrator",
        default_tenant_id="Orchestrator",
        default_bot_token="tok-default",
    )
    assert r == ("legacy_default", "platform-orchestrator", "Orchestrator", "tok-default")


def test_classic_secret_requires_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cr3t")
    assert (
        m.telegram_webhook_resolve_dispatch(
            "s3cr3t",
            default_worker_id="platform-orchestrator",
            default_tenant_id="default",
            default_bot_token="t1",
        )
        == ("legacy_default", "platform-orchestrator", "default", "t1")
    )
    assert m.telegram_webhook_resolve_dispatch(None, default_worker_id="platform-orchestrator", default_tenant_id="d", default_bot_token="t") == "reject"
    assert m.telegram_webhook_resolve_dispatch("nope", default_worker_id="platform-orchestrator", default_tenant_id="d", default_bot_token="t") == "reject"


def test_multiplex_route_picks_worker_and_token_env(monkeypatch: pytest.MonkeyPatch) -> None:
    routes = [
        {
            "secret": "bi-header",
            "worker_id": "bi_analyst",
            "tenant_id": "T1",
            "bot_token_env": "TELEGRAM_BI_ANALYST_TOKEN",
        }
    ]
    monkeypatch.setenv("DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES", json.dumps(routes))
    monkeypatch.setenv("TELEGRAM_BI_ANALYST_TOKEN", "token-bi")
    m._cached_bindings = None
    m._cached_bindings_error = None
    out = m.telegram_webhook_resolve_dispatch(
        "bi-header",
        default_worker_id="platform-orchestrator",
        default_tenant_id="default",
        default_bot_token="tok-orch",
    )
    assert isinstance(out, m.TelegramWebhookResolvedDispatch)
    assert out.worker_id == "bi_analyst"
    assert out.tenant_id == "T1"
    assert out.bot_token == "token-bi"
    assert out.forced_vault_db_path is None


def test_multiplex_route_without_tenant_uses_resolved_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    routes = [
        {
            "secret": "default-header",
            "worker_id": "default",
            "bot_token_env": "TELEGRAM_DEFAULT_TOKEN",
        }
    ]
    monkeypatch.setenv("DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES", json.dumps(routes))
    monkeypatch.setenv("TELEGRAM_DEFAULT_TOKEN", "token-default")
    m._cached_bindings = None
    m._cached_bindings_error = None

    out = m.telegram_webhook_resolve_dispatch(
        "default-header",
        default_worker_id="default",
        default_tenant_id="tenant-from-db",
        default_bot_token="tok-fallback",
    )

    assert isinstance(out, m.TelegramWebhookResolvedDispatch)
    assert out.tenant_id == "tenant-from-db"


def test_multiplex_vault_db_env_resolves_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    repo = str(tmp_path / "repo")
    db_fin = str(tmp_path / "repo" / "db" / "fin.duckdb")
    Path(db_fin).parent.mkdir(parents=True, exist_ok=True)
    routes = [
        {
            "secret": "hdr-fin",
            "worker_id": "platform-orchestrator",
            "tenant_id": "Orchestrator",
            "bot_token_env": "TELEGRAM_FINANZ_TOKEN",
            "vault_db_env": "DUCKCLAW_VAULT_DB_PATH",
        }
    ]
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", repo)
    monkeypatch.setenv("DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES", json.dumps(routes))
    monkeypatch.setenv("TELEGRAM_FINANZ_TOKEN", "tok-f")
    monkeypatch.setenv("DUCKCLAW_VAULT_DB_PATH", "db/fin.duckdb")
    m._cached_bindings = None
    m._cached_bindings_error = None
    out = m.telegram_webhook_resolve_dispatch(
        "hdr-fin",
        default_worker_id="siata_analyst",
        default_tenant_id="SIATA",
        default_bot_token="tok-s",
    )
    assert isinstance(out, m.TelegramWebhookResolvedDispatch)
    assert out.forced_vault_db_path == db_fin


def test_multiplex_legacy_still_default_process(monkeypatch: pytest.MonkeyPatch) -> None:
    routes = [
        {
            "secret": "only-bi",
            "worker_id": "bi_analyst",
            "tenant_id": "default",
            "bot_token_env": "TELEGRAM_BI_ANALYST_TOKEN",
        }
    ]
    monkeypatch.setenv("DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES", json.dumps(routes))
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "orch-legacy")
    monkeypatch.setenv("TELEGRAM_BI_ANALYST_TOKEN", "bi-tok")
    m._cached_bindings = None
    m._cached_bindings_error = None
    r = m.telegram_webhook_resolve_dispatch(
        "orch-legacy",
        default_worker_id="platform-orchestrator",
        default_tenant_id="Orchestrator",
        default_bot_token="orch-tok",
    )
    assert r == ("legacy_default", "platform-orchestrator", "Orchestrator", "orch-tok")
