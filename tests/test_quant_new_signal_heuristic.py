"""Heurística Quant: pedidos de nueva señal HITL (evita UUID inventado sin propose_trade_signal)."""

from __future__ import annotations

from duckclaw.workers.factory import (
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
