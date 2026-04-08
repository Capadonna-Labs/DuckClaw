"""Egreso Finanz: placeholder «dominio» tras tools → resumen determinístico."""

from __future__ import annotations

from duckclaw.forge.skills.quant_market_bridge import finanz_reconcile_cuentas_placeholder_reply


def test_placeholder_replaced_when_read_sql_cuentas_present() -> None:
    bad = "Aguardando el flujo de datos. Especifique el dominio: Mercado, Cuentas, o Contexto."
    messages = [
        {"role": "tool", "name": "read_sql", "content": '[{"name": "Nequi", "balance": "100.0", "currency": "COP"}]'},
        {"role": "tool", "name": "get_ibkr_portfolio", "content": "Valor total: $1.00\nCASH 1"},
    ]
    out = finanz_reconcile_cuentas_placeholder_reply(messages, bad)
    assert "Nequi" in out
    assert "Total cuentas locales en COP" in out
    assert "IBKR" in out
    assert bad not in out


def test_no_change_when_not_placeholder() -> None:
    ok = "Aquí tienes tus cuentas en COP."
    messages = [
        {"role": "tool", "name": "read_sql", "content": '[{"name": "Nequi", "balance": "100.0", "currency": "COP"}]'},
    ]
    assert finanz_reconcile_cuentas_placeholder_reply(messages, ok) == ok


def test_no_change_when_placeholder_but_no_cuentas_shape() -> None:
    bad = "Aguardando el flujo de datos. Especifique el dominio: Mercado, Cuentas, o Contexto."
    messages = [
        {"role": "tool", "name": "read_sql", "content": "[]"},
    ]
    assert finanz_reconcile_cuentas_placeholder_reply(messages, bad) == bad
