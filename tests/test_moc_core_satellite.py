"""Core-Satellite MOC+HRP helpers (átomo válvula + DTO estado delta)."""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]

from duckclaw.forge.atoms.moc_allocation import calculate_target_allocation  # noqa: E402


def test_calculate_target_allocation_hold_under_threshold() -> None:
    out = calculate_target_allocation(
        ticker="SPY",
        fase_fluido="GAS",
        hrp_weight_capped=0.25,
        equity=50_000.0,
        posicion_actual_usd=12_500.0 - 49.0,
    )
    assert out["action"] == "HOLD"


def test_calculate_target_allocation_buy_above_threshold_gas() -> None:
    out = calculate_target_allocation(
        ticker="SPY",
        fase_fluido="GAS",
        hrp_weight_capped=0.40,
        equity=50_000.0,
        posicion_actual_usd=500.0,
    )
    assert out["action"] == "BUY"
    assert pytest.approx(float(out["target_weight"])) == 0.40


def test_calculate_target_allocation_plasma_zero_valve() -> None:
    out = calculate_target_allocation(
        ticker="QQQ",
        fase_fluido="PLASMA",
        hrp_weight_capped=0.30,
        equity=100_000.0,
        posicion_actual_usd=50_000.0,
    )
    assert out["action"] == "SELL"


def test_trade_signal_mutation_strategy_name_optional() -> None:
    sys.path.insert(0, str(_REPO / "services" / "db-writer"))
    from models.quant_state_delta import TradeSignalMutation  # noqa: PLC0415

    sid = str(uuid.uuid4())
    mid = str(uuid.uuid4())
    m1 = TradeSignalMutation.model_validate(
        {
            "signal_id": sid,
            "mandate_id": mid,
            "ticker": "SPY",
            "proposed_weight": 10.5,
            "strategy_name": "moc_hrp_cfd",
        }
    )
    assert m1.strategy_name == "moc_hrp_cfd"
    m2 = TradeSignalMutation.model_validate(
        {
            "signal_id": str(uuid.uuid4()),
            "mandate_id": str(uuid.uuid4()),
            "ticker": "SPY",
            "proposed_weight": 5.0,
        }
    )
    assert m2.strategy_name == "cfd_auto"


@pytest.mark.parametrize("unknown", ["", "FOO"])
def test_unknown_phase_zero_valve_parameterized(unknown: str) -> None:
    out = calculate_target_allocation(
        ticker="X",
        fase_fluido=unknown,
        hrp_weight_capped=0.5,
        equity=40_000.0,
        posicion_actual_usd=21_000.0,
    )
    assert float(out.get("valvula") or 0) == 0.0
