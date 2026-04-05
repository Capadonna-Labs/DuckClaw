"""Heurística finanz: detectar peticiones de escritura de saldo/cuenta local."""

from duckclaw.workers.factory import _is_finanz_local_account_write_query


def test_finanz_write_query_bancolombia_saldo() -> None:
    assert _is_finanz_local_account_write_query(
        "Actualiza el saldo de la cuenta de Bancolombia a 0 COP"
    )


def test_finanz_write_query_nequi_balance() -> None:
    assert _is_finanz_local_account_write_query("Cambia el balance de Nequi a 10000")


def test_finanz_write_query_excludes_ibkr() -> None:
    assert not _is_finanz_local_account_write_query(
        "Actualiza el saldo de mi cuenta en IBKR a 0"
    )


def test_finanz_write_query_resumen_cuentas_not_write() -> None:
    assert not _is_finanz_local_account_write_query("Dame un resumen de mis cuentas bancarias")


def test_finanz_write_query_registro_gasto_not_matched() -> None:
    assert not _is_finanz_local_account_write_query(
        "Registra un gasto de 50000 en restaurante con tarjeta Bancolombia"
    )
