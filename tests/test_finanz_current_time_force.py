"""Finanz: ancla temporal con get_current_time al inicio del turno."""

from duckclaw.workers.factory import _finanz_should_force_current_time


def test_finanz_should_force_current_time_debts_and_accounts() -> None:
    assert _finanz_should_force_current_time("Dame un resumen de mis deudas")
    assert _finanz_should_force_current_time("Dame un resumen de mis cuentas")
    assert _finanz_should_force_current_time("Pasa la deuda del regalo de Laila de Mayo a Junio")


def test_finanz_should_force_current_time_negative() -> None:
    assert not _finanz_should_force_current_time("")
    assert not _finanz_should_force_current_time("gracias")
    assert not _finanz_should_force_current_time("[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]\nfoo")
    assert not _finanz_should_force_current_time("[SYSTEM_EVENT: goals tick]")
    assert not _finanz_should_force_current_time("Ejecuta el código: print(2+2)")
    assert not _finanz_should_force_current_time("run python script in sandbox")
