"""Heurística Quant: pedidos de nueva señal HITL (evita UUID inventado sin propose_trade_signal)."""

from __future__ import annotations

from duckclaw.workers.factory import (
    _quant_extract_signal_id,
    _quant_extract_tickers,
    _quant_is_proceed_like,
    _quant_user_requests_execute_approved_signal,
    _quant_user_requests_new_trade_signal,
)


def test_genera_la_senal_de_ticker_matches() -> None:
    assert _quant_user_requests_new_trade_signal("Genera la señal de META")
    assert _quant_user_requests_new_trade_signal("genera la señal de SPY")


def test_genera_senal_variants_match() -> None:
    assert _quant_user_requests_new_trade_signal("genera señal")
    assert _quant_user_requests_new_trade_signal("genera la señal")
    assert _quant_user_requests_new_trade_signal("Genera una nueva señal")


def test_execute_pending_does_not_match_new_signal() -> None:
    assert not _quant_user_requests_new_trade_signal("Ejecuta la señal pendiente")


def test_post_hitl_gateway_message_triggers_execute_tool() -> None:
    """Evidencia gateway: «ejecute» sin «ejecutar» + nombre de tool; antes forced_tool=auto."""
    body = (
        "Confirmación registrada para la señal 592876eb-7336-4fe9-bf7b-d870b5a8850c. "
        "Pide al asistente que ejecute execute_order (Finanz) o execute_approved_signal "
        "(Quant Trader) con signal_id=592876eb-7336-4fe9-bf7b-d870b5a8850c"
    )
    assert _quant_user_requests_execute_approved_signal(body)
    assert not _quant_user_requests_new_trade_signal(body)


def test_quant_proceed_like_variants_match() -> None:
    assert _quant_is_proceed_like("Procede")
    assert _quant_is_proceed_like("sigue con la ejecución")
    assert _quant_is_proceed_like("adelante")
    assert not _quant_is_proceed_like("[SYSTEM_EVENT: Revisión periódica de /goals]")
    assert not _quant_is_proceed_like("[SYSTEM_EVENT: Revisión periódica de /crons]")


def test_quant_extract_signal_id_reads_uuid() -> None:
    sid = _quant_extract_signal_id("ejecuta señal 592876eb-7336-4fe9-bf7b-d870b5a8850c ahora")
    assert sid == "592876eb-7336-4fe9-bf7b-d870b5a8850c"


def test_quant_extract_tickers_dedupes_and_filters() -> None:
    out = _quant_extract_tickers("Genera señal para AAPL y MSFT; luego AAPL")
    assert out == ["AAPL", "MSFT"]


def test_quant_extract_tickers_ignores_tarea_prefix_meta_spy() -> None:
    """Evidencia gateway: ticker=TAREA al forzar fetch; el prefijo TAREA: no es símbolo."""
    body = (
        "TAREA: El usuario acaba de confirmar con un mensaje corto (p. ej. Procede / Sí) que desea continuar "
        "con el rebalanceo HRP (META/SPY). Flujo: fetch_ib_gateway_ohlcv META/SPY; evaluate_cfd_state;"
    )
    out = _quant_extract_tickers(body)
    assert "TAREA" not in out
    assert out[0] == "META"
    assert "SPY" in out
