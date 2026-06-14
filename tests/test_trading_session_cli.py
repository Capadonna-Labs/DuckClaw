"""Tests para /trading_session CLI (incl. --update)."""

from __future__ import annotations

from duckclaw.graphs.on_the_fly_commands import (
    _merge_trading_session_goal_tickers,
    _parse_trading_session_cli,
)


def test_parse_trading_session_update_subcommand_with_tickers() -> None:
    tickers = "META,SPY,TLT,GLD,SHY,IEF,XLU,MSFT,AMD,NVDA,GOOGL,CEG,AVGO"
    parsed, err = _parse_trading_session_cli(f"update --tickers {tickers}")
    assert err is None
    assert parsed is not None
    assert parsed.update is True
    assert parsed.mode is None
    assert parsed.tickers_csv == tickers


def test_parse_trading_session_update_flag_requires_tickers() -> None:
    parsed, err = _parse_trading_session_cli("--update")
    assert parsed is None
    assert err is not None
    assert "tickers" in (err or "").lower()


def test_parse_trading_session_update_rejects_mode() -> None:
    parsed, err = _parse_trading_session_cli("--update --mode paper --tickers SPY")
    assert parsed is None
    assert err is not None
    assert "mode" in (err or "").lower()


def test_parse_trading_session_anchor_equity_on_new_session() -> None:
    parsed, err = _parse_trading_session_cli("--mode paper --tickers SPY --anchor-equity 916645")
    assert err is None
    assert parsed is not None
    assert parsed.anchor_equity == 916645.0


def test_parse_trading_session_update_anchor_only() -> None:
    parsed, err = _parse_trading_session_cli("--update --anchor_equity 916645")
    assert err is None
    assert parsed is not None
    assert parsed.update is True
    assert parsed.anchor_equity == 916645.0
    assert parsed.tickers_csv == ""


def test_parse_trading_session_anchor_equity_rejects_non_positive() -> None:
    parsed, err = _parse_trading_session_cli("--mode paper --anchor-equity 0")
    assert parsed is None
    assert err is not None


def test_merge_trading_session_goal_tickers_preserves_objective() -> None:
    existing = {"objective": "rebalance_hrp", "max_drawdown_pct": 2.0, "tickers": ["SPY"]}
    merged = _merge_trading_session_goal_tickers(existing, "NVDA,META")
    import json

    goal = json.loads(merged)
    assert goal["objective"] == "rebalance_hrp"
    assert goal["tickers"] == ["NVDA", "META"]

