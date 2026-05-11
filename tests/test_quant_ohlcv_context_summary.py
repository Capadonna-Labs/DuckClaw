"""OHLCV en SUMMARIZE_*: heurística env + helper (Quant Trader)."""

from __future__ import annotations

import pytest


def test_summarize_allows_forced_ohlcv_only_when_env_and_quant_and_heuristic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.workers import factory as f

    body = "[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]\nDescarga velas OHLCV para SPY"
    monkeypatch.setenv("DUCKCLAW_QUANT_OHLCV_ON_CONTEXT_SUMMARY", "1")
    assert f._quant_summarize_allows_forced_ohlcv_fetch(body, "quant_trader")
    monkeypatch.delenv("DUCKCLAW_QUANT_OHLCV_ON_CONTEXT_SUMMARY", raising=False)
    assert not f._quant_summarize_allows_forced_ohlcv_fetch(body, "quant_trader")


def test_summarize_forced_ohlcv_requires_finanz_style_keyword(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.workers import factory as f

    # Sin palabras clave ohlcv/velas ni ticker A–Z en el cuerpo (el prefijo SYSTEM_DIRECTIVE
    # puede contener tokens en mayúsculas: no usar «OHLCV» en el cuerpo del test).
    body = "[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]\nSolo texto narrativo sin símbolos."
    monkeypatch.setenv("DUCKCLAW_QUANT_OHLCV_ON_CONTEXT_SUMMARY", "1")
    assert not f._quant_summarize_allows_forced_ohlcv_fetch(body, "quant_trader")


def test_finanz_never_uses_quant_summarize_ohlcv_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.workers import factory as f

    body = "[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]\nvelas SPY"
    monkeypatch.setenv("DUCKCLAW_QUANT_OHLCV_ON_CONTEXT_SUMMARY", "1")
    assert not f._quant_summarize_allows_forced_ohlcv_fetch(body, "finanz")
