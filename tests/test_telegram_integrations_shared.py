"""Tests para duckclaw.integrations.telegram (shared)."""

from __future__ import annotations

import pytest


def test_telegram_webhook_secret_invalid_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "expected-secret")
    from duckclaw.integrations.telegram import is_valid_telegram_webhook_secret_token

    assert is_valid_telegram_webhook_secret_token("expected-secret") is True
    assert is_valid_telegram_webhook_secret_token("wrong") is False
    assert is_valid_telegram_webhook_secret_token(None) is False


def test_telegram_webhook_secret_skipped_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    from duckclaw.integrations.telegram import is_valid_telegram_webhook_secret_token

    assert is_valid_telegram_webhook_secret_token(None) is True
    assert is_valid_telegram_webhook_secret_token("") is True
