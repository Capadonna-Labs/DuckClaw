"""Enrutamiento multi-bot por cabecera secret_token (DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES)."""

from __future__ import annotations

import json

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
        default_worker_id="finanz",
        default_tenant_id="Finanzas",
        default_bot_token="tok-default",
    )
    assert r == ("legacy_default", "finanz", "Finanzas", "tok-default")


def test_classic_secret_requires_match(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "s3cr3t")
    assert (
        m.telegram_webhook_resolve_dispatch(
            "s3cr3t",
            default_worker_id="finanz",
            default_tenant_id="default",
            default_bot_token="t1",
        )
        == ("legacy_default", "finanz", "default", "t1")
    )
    assert m.telegram_webhook_resolve_dispatch(None, default_worker_id="finanz", default_tenant_id="d", default_bot_token="t") == "reject"
    assert m.telegram_webhook_resolve_dispatch("nope", default_worker_id="finanz", default_tenant_id="d", default_bot_token="t") == "reject"


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
        default_worker_id="finanz",
        default_tenant_id="default",
        default_bot_token="tok-finanz",
    )
    assert isinstance(out, m.TelegramWebhookResolvedDispatch)
    assert out.worker_id == "bi_analyst"
    assert out.tenant_id == "T1"
    assert out.bot_token == "token-bi"


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
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "finanz-legacy")
    monkeypatch.setenv("TELEGRAM_BI_ANALYST_TOKEN", "bi-tok")
    m._cached_bindings = None
    m._cached_bindings_error = None
    r = m.telegram_webhook_resolve_dispatch(
        "finanz-legacy",
        default_worker_id="finanz",
        default_tenant_id="Finanzas",
        default_bot_token="finanz-tok",
    )
    assert r == ("legacy_default", "finanz", "Finanzas", "finanz-tok")
