"""calculate_synthetic_greeks: validaciones, CASH bypass, sandbox parse (mocks)."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from duckclaw.graphs.sandbox import ExecutionResult
from duckclaw.forge.skills.quant_trader_bridge import (
    _build_greeks_sandbox_script,
    _calculate_synthetic_greeks_impl,
)


def test_build_greeks_script_contains_bsm_and_formulas() -> None:
    s = _build_greeks_sandbox_script(100.0, 100.0, 0.25, 0.05, 0.2, "call")
    assert "bsm_synthetic" in s
    assert "norm.cdf" in s or "norm.pdf" in s
    assert "json.dumps(result)" in s


@pytest.mark.parametrize(
    "ticker",
    ["CASH", "$CASH", " cash "],
)
def test_cash_bypass_no_sandbox(monkeypatch: pytest.MonkeyPatch, ticker: str) -> None:
    called: dict[str, bool] = {"sandbox": False}

    def _no_sandbox(*_a: Any, **_k: Any) -> ExecutionResult:
        called["sandbox"] = True
        return ExecutionResult(exit_code=0, stdout="{}", stderr="")

    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.run_in_sandbox",
        _no_sandbox,
    )
    raw = _calculate_synthetic_greeks_impl(
        MagicMock(), MagicMock(), ticker=ticker, S=1.0, K=1.0, T=1.0, r=0.01, sigma=0.2
    )
    assert called["sandbox"] is False
    out = json.loads(raw)
    assert out.get("valid") is False
    assert out.get("reason") == "CASH"


def test_s_must_be_positive() -> None:
    raw = _calculate_synthetic_greeks_impl(
        MagicMock(), MagicMock(), ticker="SPY", S=0.0, K=100.0, T=1.0, r=0.05, sigma=0.2
    )
    assert json.loads(raw) == {"error": "S debe ser > 0"}


def test_t_non_positive_returns_zeros() -> None:
    raw = _calculate_synthetic_greeks_impl(
        MagicMock(), MagicMock(), ticker="SPY", S=100.0, K=100.0, T=0.0, r=0.05, sigma=0.2
    )
    out = json.loads(raw)
    assert out.get("valid") is False
    assert out.get("reason") == "T<=0"


def test_sigma_non_positive_returns_zeros() -> None:
    raw = _calculate_synthetic_greeks_impl(
        MagicMock(), MagicMock(), ticker="SPY", S=100.0, K=100.0, T=0.25, r=0.05, sigma=0.0
    )
    out = json.loads(raw)
    assert out.get("valid") is False
    assert out.get("reason") == "sigma<=0"


def test_sandbox_failure_returns_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.run_in_sandbox",
        lambda *_a, **_k: ExecutionResult(exit_code=1, stdout="", stderr="boom"),
    )
    raw = _calculate_synthetic_greeks_impl(
        MagicMock(), MagicMock(), ticker="SPY", S=100.0, K=100.0, T=0.25, r=0.05, sigma=0.2
    )
    out = json.loads(raw)
    assert out.get("error") == "SANDBOX_EXECUTION_FAILED"


def test_sandbox_success_adds_ticker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.run_in_sandbox",
        lambda *_a, **_k: ExecutionResult(
            exit_code=0,
            stdout=json.dumps({"delta": 0.5, "gamma": 0.01, "vega": 0.2, "theta": -0.1, "valid": True}),
            stderr="",
        ),
    )
    raw = _calculate_synthetic_greeks_impl(
        MagicMock(), MagicMock(), ticker="QQQ", S=100.0, K=100.0, T=0.25, r=0.05, sigma=0.2
    )
    out = json.loads(raw)
    assert out.get("ticker") == "QQQ"
    assert out.get("delta") == 0.5


def test_parse_failure_garbage_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.run_in_sandbox",
        lambda *_a, **_k: ExecutionResult(exit_code=0, stdout="not json", stderr=""),
    )
    raw = _calculate_synthetic_greeks_impl(
        MagicMock(), MagicMock(), ticker="SPY", S=100.0, K=100.0, T=0.25, r=0.05, sigma=0.2
    )
    out = json.loads(raw)
    assert out.get("error") == "SANDBOX_PARSE_FAILED"


def test_parse_failure_multiline_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    stdout = "noise\n{\"delta\": 1.0}\n"
    monkeypatch.setattr(
        "duckclaw.forge.skills.quant_trader_bridge.run_in_sandbox",
        lambda *_a, **_k: ExecutionResult(exit_code=0, stdout=stdout, stderr=""),
    )
    raw = _calculate_synthetic_greeks_impl(
        MagicMock(), MagicMock(), ticker="SPY", S=100.0, K=100.0, T=0.25, r=0.05, sigma=0.2
    )
    out = json.loads(raw)
    assert out.get("delta") == 1.0
