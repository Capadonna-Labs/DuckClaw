"""DOTENV_OVERRIDE_KEYS: .env gana sobre PM2 stale para URLs IBKR."""

import os

from duckclaw.env_secrets import DOTENV_OVERRIDE_KEYS, apply_dotenv_overrides_to_os_environ


def test_ibkr_portfolio_url_in_dotenv_override_keys() -> None:
    assert "IBKR_PORTFOLIO_API_URL" in DOTENV_OVERRIDE_KEYS
    assert "CAPADONNA_SSH_HOST" in DOTENV_OVERRIDE_KEYS


def test_apply_dotenv_overrides_replaces_stale_pm2_ibkr_url(monkeypatch) -> None:
    monkeypatch.setenv("IBKR_PORTFOLIO_API_URL", "http://100.97.151.69:8002/api/portfolio/summary")
    apply_dotenv_overrides_to_os_environ(
        {"IBKR_PORTFOLIO_API_URL": "http://100.75.4.17:8002/api/portfolio/summary"}
    )
    assert os.environ["IBKR_PORTFOLIO_API_URL"] == "http://100.75.4.17:8002/api/portfolio/summary"
