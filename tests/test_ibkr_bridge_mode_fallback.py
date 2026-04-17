"""Reintento paper/live ante snapshot_unavailable en ibkr_bridge."""

from __future__ import annotations

import json

import pytest

from duckclaw.forge.skills import ibkr_bridge as ib


def test_resolve_retries_live_when_paper_snapshot_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IBKR_ACCOUNT_MODE", "paper")
    monkeypatch.delenv("IBKR_ACCOUNT_MODE_ALT_FALLBACK", raising=False)

    def fake_fetch(
        api_url: str,
        api_key: str,
        positions_url: str,
        mode: str,
    ) -> dict:
        if mode == "paper":
            return {
                "portfolio": [],
                "total_value": 0,
                "error": "snapshot_unavailable",
            }
        return {
            "portfolio": [{"symbol": "SPY", "quantity": 1, "market_value": 100.0}],
            "total_value": 100.0,
        }

    monkeypatch.setattr(ib, "_ibkr_fetch_portfolio_payload", fake_fetch)
    data, effective, configured = ib._ibkr_resolve_payload_with_optional_alt(
        "http://x/summary", "k", ""
    )
    assert configured == "paper"
    assert effective == "live"
    assert ib._ibkr_snapshot_has_substance(data)
    assert data.get("total_value") == 100.0


def test_resolve_no_retry_when_fallback_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("IBKR_ACCOUNT_MODE", "paper")
    monkeypatch.setenv("IBKR_ACCOUNT_MODE_ALT_FALLBACK", "0")

    calls: list[str] = []

    def fake_fetch(
        api_url: str,
        api_key: str,
        positions_url: str,
        mode: str,
    ) -> dict:
        calls.append(mode)
        return {"portfolio": [], "total_value": 0, "error": "snapshot_unavailable"}

    monkeypatch.setattr(ib, "_ibkr_fetch_portfolio_payload", fake_fetch)
    data, effective, configured = ib._ibkr_resolve_payload_with_optional_alt(
        "http://x/summary", "k", ""
    )
    assert calls == ["paper"]
    assert effective == "paper"
    assert configured == "paper"
    assert json.dumps(data).find("snapshot_unavailable") >= 0
