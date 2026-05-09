"""Finanz: IBKR live-only snapshot y aviso sesión Quant paper."""

from __future__ import annotations

from pathlib import Path

import pytest

from duckclaw import DuckClaw
from duckclaw.forge.skills import ibkr_bridge as ib


def test_resolve_live_only_no_paper_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def fake_fetch(
        api_url: str,
        api_key: str,
        positions_url: str,
        mode: str,
    ) -> dict:
        calls.append(mode)
        return {"portfolio": [], "total_value": 1.0}

    monkeypatch.setattr(ib, "_ibkr_fetch_portfolio_payload", fake_fetch)
    data, effective, configured = ib._ibkr_resolve_payload_live_only("http://x/summary", "k", "")
    assert calls == ["live"]
    assert effective == "live"
    assert configured == "live"
    assert data.get("total_value") == 1.0


def test_finanz_paper_session_notice_when_active_paper(tmp_path: Path) -> None:
    db_path = tmp_path / "f.duckdb"
    with DuckClaw(str(db_path), read_only=False) as db:
        db.execute("CREATE SCHEMA IF NOT EXISTS quant_core")
        db.execute(
            """
            CREATE TABLE quant_core.trading_sessions (
              id VARCHAR PRIMARY KEY,
              mode VARCHAR NOT NULL,
              tickers VARCHAR NOT NULL DEFAULT '',
              status VARCHAR NOT NULL DEFAULT 'ACTIVE'
            )
            """
        )
        db.execute(
            "INSERT INTO quant_core.trading_sessions (id, mode, tickers, status) "
            "VALUES ('active', 'paper', 'SPY,META', 'ACTIVE')"
        )
    text = ib.finanz_active_paper_quant_session_notice(str(db_path))
    assert "paper" in text.lower()
    assert "quant" in text.lower() or "playbook" in text.lower()
    assert "SPY" in text or "META" in text


def test_infer_snapshot_paper_from_du_account_id() -> None:
    assert ib._ibkr_infer_snapshot_account_mode({"account_id": "DU1234567", "total_value": 1.0}) == "paper"


def test_infer_snapshot_from_ib_env() -> None:
    assert ib._ibkr_infer_snapshot_account_mode({"ib_env": "paper", "portfolio": []}) == "paper"
    assert ib._ibkr_infer_snapshot_account_mode({"ib_env": "live", "portfolio": []}) == "live"


def test_finanz_impl_unverified_when_no_account_metadata(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("IBKR_PORTFOLIO_API_URL", "http://example/summary")
    monkeypatch.setenv("IBKR_PORTFOLIO_API_KEY", "k")
    monkeypatch.delenv("IBKR_FINANZ_ASSUMED_SNAPSHOT_MODE", raising=False)

    def fake_live_only(url: str, key: str, pos: str) -> tuple[dict, str, str]:
        return ({"portfolio": [], "total_value": 42.0}, "live", "live")

    monkeypatch.setattr(ib, "_ibkr_resolve_payload_live_only", fake_live_only)
    out = ib._get_ibkr_portfolio_finanz_impl(str(tmp_path / "u.duckdb"))
    assert "modo no verificado" in out.lower()
    assert "no verificado (api sin metadatos de cuenta)" in out.lower()


def test_finanz_impl_assumed_paper_when_env_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("IBKR_PORTFOLIO_API_URL", "http://example/summary")
    monkeypatch.setenv("IBKR_PORTFOLIO_API_KEY", "k")
    monkeypatch.setenv("IBKR_FINANZ_ASSUMED_SNAPSHOT_MODE", "paper")

    def fake_live_only(url: str, key: str, pos: str) -> tuple[dict, str, str]:
        return ({"portfolio": [], "total_value": 1.0}, "live", "live")

    monkeypatch.setattr(ib, "_ibkr_resolve_payload_live_only", fake_live_only)
    out = ib._get_ibkr_portfolio_finanz_impl(str(tmp_path / "p.duckdb"))
    assert "IBKR_FINANZ_ASSUMED_SNAPSHOT_MODE=paper" in out
    assert "no muestra saldos" in out.lower()
    assert "valor total" not in out.lower()
    assert "$1" not in out


def test_finanz_impl_labels_paper_when_payload_suggests_paper(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("IBKR_PORTFOLIO_API_URL", "http://example/summary")
    monkeypatch.setenv("IBKR_PORTFOLIO_API_KEY", "k")

    def fake_live_only(url: str, key: str, pos: str) -> tuple[dict, str, str]:
        return (
            {"portfolio": [], "total_value": 100.0, "account_id": "DU999"},
            "live",
            "live",
        )

    monkeypatch.setattr(ib, "_ibkr_resolve_payload_live_only", fake_live_only)
    out = ib._get_ibkr_portfolio_finanz_impl(str(tmp_path / "none.duckdb"))
    assert "paper" in out.lower()
    assert "no muestra saldos" in out.lower()
    assert "$100" not in out
    assert "valor total" not in out.lower()


def test_finanz_quant_notice_when_paper_session_ibkr_suppressed(tmp_path: Path) -> None:
    db_path = tmp_path / "q.duckdb"
    with DuckClaw(str(db_path), read_only=False) as db:
        db.execute("CREATE SCHEMA IF NOT EXISTS quant_core")
        db.execute(
            """
            CREATE TABLE quant_core.trading_sessions (
              id VARCHAR PRIMARY KEY,
              mode VARCHAR NOT NULL,
              tickers VARCHAR NOT NULL DEFAULT '',
              status VARCHAR NOT NULL DEFAULT 'ACTIVE'
            )
            """
        )
        db.execute(
            "INSERT INTO quant_core.trading_sessions (id, mode, tickers, status) "
            "VALUES ('active', 'paper', 'SPY', 'ACTIVE')"
        )
    text = ib.finanz_active_paper_quant_session_notice(
        str(db_path), ibkr_numeric_snapshot_shown=False
    )
    assert "no hay cifras del broker" in text.lower()
    assert "solo cuenta live" not in text.lower()


def test_finanz_paper_session_notice_empty_when_live(tmp_path: Path) -> None:
    db_path = tmp_path / "g.duckdb"
    with DuckClaw(str(db_path), read_only=False) as db:
        db.execute("CREATE SCHEMA IF NOT EXISTS quant_core")
        db.execute(
            """
            CREATE TABLE quant_core.trading_sessions (
              id VARCHAR PRIMARY KEY,
              mode VARCHAR NOT NULL,
              tickers VARCHAR NOT NULL DEFAULT '',
              status VARCHAR NOT NULL DEFAULT 'ACTIVE'
            )
            """
        )
        db.execute(
            "INSERT INTO quant_core.trading_sessions (id, mode, tickers, status) "
            "VALUES ('active', 'live', 'SPY', 'ACTIVE')"
        )
    assert ib.finanz_active_paper_quant_session_notice(str(db_path)) == ""
