"""Acumulador intradía MOC: hints, ventana RTH, handler DuckDB, bridge Quant."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import duckdb
import pytest
from zoneinfo import ZoneInfo

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO / "packages" / "agents" / "src") not in sys.path:
    sys.path.insert(0, str(_REPO / "packages" / "agents" / "src"))
_DW = _REPO / "services" / "db-writer"
if str(_DW) not in sys.path:
    sys.path.insert(0, str(_DW))

from duckclaw.forge.atoms.moc_intraday_hints import (  # noqa: E402
    apply_intraday_accum_hints_to_allocation,
    merge_intraday_accum_payload,
)
from duckclaw.forge.skills.intraday_accum_window import (  # noqa: E402
    inside_reference_accumulation_trading_week_cot,
    inside_reference_equity_rth_cot,
)
from duckclaw.forge.skills.quant_tool_context import (  # noqa: E402
    set_quant_tool_db_path,
    set_quant_tool_tenant_id,
    set_quant_tool_user_id,
)
from duckclaw.forge.skills.quant_trader_bridge import (  # noqa: E402
    _accumulate_moc_intraday_state_impl,
    _propose_trade_signal_impl,
)

from models.quant_state_delta import IntradayMocAccumMutation, QuantStateDelta  # noqa: E402
from quant_state_delta_handler import _INTRADAY_MOC_ACCUM_DDL, _apply_delta  # noqa: E402


@pytest.fixture(autouse=True)
def _quant_ignore_rth_for_accum_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """Barrera dev: accumulate y varios checks no dependen del reloj del runner."""
    monkeypatch.setenv("DUCKCLAW_QUANT_IGNORE_MOC_TIME_GATES", "1")


@pytest.fixture
def accum_duck() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute("CREATE SCHEMA IF NOT EXISTS quant_core;")
    con.execute(_INTRADAY_MOC_ACCUM_DDL.strip())
    yield con
    con.close()


def _quant_delta_accum(mutation: dict) -> QuantStateDelta:
    return QuantStateDelta(
        tenant_id="default",
        delta_type="INTRADAY_MOC_ACCUM_UPSERT",
        user_id="u1",
        target_db_path="/tmp/quant.duckdb",
        mutation=mutation,
    )


def test_merge_intraday_accum_payload_superficial() -> None:
    merged = merge_intraday_accum_payload('{"a":1}', {"a": 2, "notes": "x"})
    assert merged["a"] == 2
    assert merged["notes"] == "x"


def test_intraday_moc_accum_mutation_model() -> None:
    m = IntradayMocAccumMutation(session_uid="sess-1", ticker="SPY", patch={"weight_scale": 0.95})
    assert m.session_uid == "sess-1"
    assert m.patch["weight_scale"] == 0.95


def test_apply_intraday_accum_hints_weight_scale() -> None:
    base = {
        "action": "BUY",
        "delta_usd": 1000.0,
        "target_weight": 0.1,
        "hrp_weight": 0.15,
        "valvula": 0.05,
        "fase": "GAS",
        "rationale": "base",
    }
    out = apply_intraday_accum_hints_to_allocation(
        base,
        {"weight_scale": 0.5},
        hrp_weight_capped=0.15,
        equity=100_000.0,
        posicion_actual_usd=2000.0,
    )
    assert abs(float(out.get("target_weight") or 0.0) - 0.05) < 1e-9
    assert "weight_scale" in str(out.get("rationale") or "")


def test_inside_reference_rth_weekend() -> None:
    sat = datetime(2026, 5, 2, 10, 0, 0, tzinfo=ZoneInfo("America/Bogota"))
    ok, reason, _meta = inside_reference_equity_rth_cot(sat)
    assert ok is False
    assert reason == "WEEKEND"


def test_inside_reference_rth_weekday_noon() -> None:
    fri = datetime(2026, 5, 1, 12, 0, 0, tzinfo=ZoneInfo("America/Bogota"))
    ok, _, _ = inside_reference_equity_rth_cot(fri)
    assert ok is True


def test_inside_accumulation_weekday_before_rth_open() -> None:
    """Acumulación MOC: lun–vie permitido antes de 08:30 (p. ej. optimizar pre-apertura)."""
    mon = datetime(2026, 5, 4, 7, 18, 0, tzinfo=ZoneInfo("America/Bogota"))
    ok, reason, meta = inside_reference_accumulation_trading_week_cot(mon)
    assert ok is True
    assert reason == ""
    assert meta.get("accum_policy") == "anytime_cot_including_weekend"


def test_inside_accumulation_weekend_allowed_by_default() -> None:
    sat = datetime(2026, 5, 2, 10, 0, 0, tzinfo=ZoneInfo("America/Bogota"))
    ok, reason, meta = inside_reference_accumulation_trading_week_cot(sat)
    assert ok is True
    assert reason == ""
    assert meta.get("accum_policy") == "anytime_cot_including_weekend"


def test_inside_accumulation_weekend_blocked_when_env_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_MOC_ACCUM_BLOCK_WEEKEND", "1")
    sat = datetime(2026, 5, 2, 10, 0, 0, tzinfo=ZoneInfo("America/Bogota"))
    ok, reason, _ = inside_reference_accumulation_trading_week_cot(sat)
    assert ok is False
    assert reason == "WEEKEND"


def test_accumulate_enqueues_saturday_without_ignore_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_QUANT_IGNORE_MOC_TIME_GATES", raising=False)
    monkeypatch.delenv("DUCKCLAW_MOC_ACCUM_BLOCK_WEEKEND", raising=False)
    sat = datetime(2026, 5, 2, 11, 0, 0, tzinfo=ZoneInfo("America/Bogota"))
    monkeypatch.setattr(
        "duckclaw.forge.skills.intraday_accum_window.reference_rth_cot_now",
        lambda: sat,
    )
    db = _FakeDbActive()
    set_quant_tool_tenant_id("default")
    set_quant_tool_user_id("u1")
    set_quant_tool_db_path(db._path)
    pushed: list[dict] = []

    def _push(p: dict, **__: object) -> bool:
        pushed.append(dict(p))
        return True

    monkeypatch.setattr("duckclaw.forge.skills.quant_trader_bridge.push_quant_state_delta_sync", _push)
    raw = _accumulate_moc_intraday_state_impl(
        db,
        ticker="QQQ",
        accumulation_patch={"notes": "weekend tweak"},
        trading_date="2026-05-02",
    )
    out = json.loads(raw)
    assert out.get("status") == "enqueued"
    assert pushed and pushed[0].get("delta_type") == "INTRADAY_MOC_ACCUM_UPSERT"


def test_accumulate_enqueues_monday_pre_rth_without_ignore_gates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_QUANT_IGNORE_MOC_TIME_GATES", raising=False)
    early = datetime(2026, 5, 4, 7, 18, 0, tzinfo=ZoneInfo("America/Bogota"))
    monkeypatch.setattr(
        "duckclaw.forge.skills.intraday_accum_window.reference_rth_cot_now",
        lambda: early,
    )
    db = _FakeDbActive()
    set_quant_tool_tenant_id("default")
    set_quant_tool_user_id("u1")
    set_quant_tool_db_path(db._path)
    pushed: list[dict] = []

    def _push(p: dict, **__: object) -> bool:
        pushed.append(dict(p))
        return True

    monkeypatch.setattr("duckclaw.forge.skills.quant_trader_bridge.push_quant_state_delta_sync", _push)
    raw = _accumulate_moc_intraday_state_impl(
        db,
        ticker="SPY",
        accumulation_patch={"weight_scale": 0.9},
        trading_date="2026-05-04",
    )
    out = json.loads(raw)
    assert out.get("status") == "enqueued"
    assert pushed and pushed[0].get("delta_type") == "INTRADAY_MOC_ACCUM_UPSERT"


def test_handler_intraday_accum_upsert_merge(accum_duck: duckdb.DuckDBPyConnection) -> None:
    con = accum_duck
    d1 = _quant_delta_accum(
        {"session_uid": "su-a", "ticker": "QQQ", "patch": {"weight_scale": 0.8}, "trading_date": "2026-05-01"}
    )
    _apply_delta(con, d1)
    d2 = _quant_delta_accum(
        {"session_uid": "su-a", "ticker": "QQQ", "patch": {"notes": "n1"}, "trading_date": "2026-05-01"}
    )
    _apply_delta(con, d2)
    row = con.execute(
        "SELECT payload FROM quant_core.intraday_moc_accum WHERE session_uid = ? AND ticker = ? AND trading_date = ?::DATE",
        ["su-a", "QQQ", "2026-05-01"],
    ).fetchone()
    assert row is not None
    pj = row[0]
    if isinstance(pj, str):
        data = json.loads(pj)
    else:
        data = dict(pj)  # type: ignore[arg-type]
    assert float(data["weight_scale"]) == 0.8
    assert data["notes"] == "n1"


def test_handler_intraday_accum_rejects_when_finalized(accum_duck: duckdb.DuckDBPyConnection) -> None:
    con = accum_duck
    d1 = _quant_delta_accum(
        {"session_uid": "su-b", "ticker": "SPY", "patch": {"weight_scale": 1.0}, "trading_date": "2026-05-06"}
    )
    _apply_delta(con, d1)
    con.execute(
        "UPDATE quant_core.intraday_moc_accum SET finalized_at = now() "
        "WHERE session_uid = ? AND ticker = ? AND trading_date = ?::DATE",
        ["su-b", "SPY", "2026-05-06"],
    )
    d2 = _quant_delta_accum(
        {"session_uid": "su-b", "ticker": "SPY", "patch": {"notes": "late"}, "trading_date": "2026-05-06"}
    )
    with pytest.raises(ValueError, match="finalizado"):
        _apply_delta(con, d2)


class _FakeDbActive:
    """Mínimo DuckClaw-like para accumulate (sesión ACTIVE)."""

    _path = "/tmp/test_intraday_accum.duckdb"

    def query(self, sql: str) -> str:
        if "SUM(balance)" in sql:
            return json.dumps([{"liquid": 10000.0}])
        if "quant_core.trading_sessions" in sql and "id = 'active'" in sql:
            return json.dumps(
                [
                    {
                        "mode": "paper",
                        "tickers": "SPY,QQQ",
                        "status": "ACTIVE",
                        "session_uid": "sess-intra-1",
                        "session_goal": None,
                    }
                ]
            )
        return json.dumps([])


def test_accumulate_moc_intraday_enqueues_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    db = _FakeDbActive()
    set_quant_tool_tenant_id("default")
    set_quant_tool_user_id("u1")
    set_quant_tool_db_path(db._path)
    pushed: list[dict] = []

    def _push(p: dict, **__: object) -> bool:
        pushed.append(dict(p))
        return True

    monkeypatch.setattr("duckclaw.forge.skills.quant_trader_bridge.push_quant_state_delta_sync", _push)
    raw = _accumulate_moc_intraday_state_impl(
        db,
        ticker="SPY",
        accumulation_patch={"weight_scale": 0.88, "evil_key": 999},
        trading_date="2026-05-06",
    )
    out = json.loads(raw)
    assert out.get("status") == "enqueued"
    assert pushed and pushed[0].get("delta_type") == "INTRADAY_MOC_ACCUM_UPSERT"
    patch = pushed[0]["mutation"]["patch"]
    assert patch.get("weight_scale") == 0.88
    assert "evil_key" not in patch


def test_propose_trade_signal_moc_batch_auto_chains_like_cfd_auto(monkeypatch: pytest.MonkeyPatch) -> None:
    class _DbPendingHitl(_FakeDbActive):
        def query(self, sql: str) -> str:
            if "FROM finance_worker.trade_signals" in sql and "human_approved" in sql:
                return json.dumps(
                    [
                        {
                            "human_approved": False,
                            "status": "AWAITING_HITL",
                            "ticker": "SPY",
                            "signal_type": "ENTRY",
                            "proposed_weight": 5.0,
                            "mandate_id": "33333333-3333-3333-3333-333333333333",
                        }
                    ]
                )
            return super().query(sql)

    monkeypatch.delenv("DUCKCLAW_QUANT_IGNORE_MOC_TIME_GATES", raising=False)
    db = _DbPendingHitl()
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge._quant_now_bogota",
        lambda: datetime(2026, 5, 1, 14, 45, 0, tzinfo=ZoneInfo("America/Bogota")),
    )
    set_quant_tool_tenant_id("default")
    set_quant_tool_user_id("u1")
    set_quant_tool_db_path(db._path)
    from duckclaw.forge.skills.quant_tool_context import (  # noqa: PLC0415 — after path
        note_quant_market_evidence_ticker,
        set_quant_tool_chat_id,
    )

    set_quant_tool_chat_id("tg_moc_batch_auto")
    note_quant_market_evidence_ticker("SPY")
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge._max_weight_pct_limit",
        lambda: 10.0,
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.push_quant_state_delta_sync",
        lambda _p, **__: True,
    )
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge._wait_until_signal_row_visible",
        lambda _db, _sid, **kwargs: True,
    )
    monkeypatch.delenv("IBKR_EXECUTE_ORDER_URL", raising=False)
    monkeypatch.setenv("DUCKCLAW_QUANT_AUTO_EXECUTE_SIGNALS", "1")
    monkeypatch.setenv("DUCKCLAW_MOC_BATCH_AUTO_EXECUTE", "1")
    monkeypatch.delenv("DUCKCLAW_QUANT_AUTO_EXECUTE_IGNORE_MOC_WINDOW", raising=False)
    monkeypatch.delenv("DUCKCLAW_QUANT_AUTO_EXECUTE_MOC_WINDOW", raising=False)
    out = json.loads(
        _propose_trade_signal_impl(
            db,
            mandate_id="11111111-1111-1111-1111-111111111111",
            ticker="SPY",
            weight=5.0,
            strategy_name="moc_hrp_cfd",
        )
    )
    assert out.get("auto_executed") is True
    ex = out.get("execution")
    assert isinstance(ex, dict) and ex.get("status") == "simulated"
