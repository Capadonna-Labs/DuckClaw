# tests/test_telegram_path_webhook_routes.py
"""Rutas /webhook/finanz y /webhook/trabajo: mismo host Tailscale, bots con URLs distintas."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
API_GATEWAY_DIR = REPO_ROOT / "services" / "api-gateway"
if str(API_GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(API_GATEWAY_DIR))

from routers import telegram_inbound_webhook as tiw


@pytest.fixture()
def clear_webhook_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in (
        "TELEGRAM_WEBHOOK_SECRET_FINANZ",
        "TELEGRAM_WEBHOOK_SECRET_TRABAJO",
        "TELEGRAM_WEBHOOK_SECRET",
    ):
        monkeypatch.delenv(k, raising=False)


def test_path_secret_finanz_accepts_shared_legacy_when_configured(
    monkeypatch: pytest.MonkeyPatch, clear_webhook_secrets: None
) -> None:
    secret = "test-secret-finanz-abc"
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", secret)
    assert tiw._webhook_secret_ok_finanz_path(secret) is True
    assert tiw._webhook_secret_ok_finanz_path("wrong") is False
    assert tiw._webhook_secret_ok_finanz_path("") is False


def test_path_secret_finanz_prefers_telegram_webhook_secret_finanz(
    monkeypatch: pytest.MonkeyPatch, clear_webhook_secrets: None
) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "legacy-shared")
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET_FINANZ", "only-finanz")
    assert tiw._webhook_secret_ok_finanz_path("only-finanz") is True
    assert tiw._webhook_secret_ok_finanz_path("legacy-shared") is False


def test_path_secret_trabajo(
    monkeypatch: pytest.MonkeyPatch, clear_webhook_secrets: None
) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET_TRABAJO", "job-secret")
    assert tiw._webhook_secret_ok_trabajo_path("job-secret") is True
    assert tiw._webhook_secret_ok_trabajo_path("nope") is False


def test_path_secret_dev_mode_allows_without_env(clear_webhook_secrets: None) -> None:
    assert tiw._webhook_secret_ok_finanz_path(None) is True
    assert tiw._webhook_secret_ok_trabajo_path("") is True


def test_path_route_family_normalizes() -> None:
    assert tiw._telegram_path_route_family(None) is None
    assert tiw._telegram_path_route_family("finanz") == "finanz"
    assert tiw._telegram_path_route_family("Finanzas") == "finanz"
    assert tiw._telegram_path_route_family("job-hunter") == "trabajo"
