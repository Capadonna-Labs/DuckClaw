"""read_pool: envoltorio finanz deudas con total sin doble conteo Mac Mini agregado + cuotas."""

import json
from unittest.mock import Mock

from duckclaw.workers import read_pool


def test_maybe_wrap_finanz_deudas_dedup_mac_mini_aggregate_plus_cuotas() -> None:
    spec = Mock(worker_id="finanz", logical_worker_id=None, schema_name="finance_worker")
    rows = [
        {
            "id": "18",
            "description": "Mac Mini - TC Bancolombia - 8 cuotas mensuales",
            "amount": "2360000.0",
            "creditor": "TC Bancolombia",
        },
        {"id": "5", "description": "Mac Mini - Cuota Abril 2026", "amount": "295000.0", "creditor": "TC Bancolombia"},
        {"id": "6", "description": "Mac Mini - Cuota Mayo 2026", "amount": "295000.0", "creditor": "TC Bancolombia"},
        {"id": "13", "description": "Escritorio - Cuota Marzo 2026", "amount": "215000.0", "creditor": "Mamá"},
        {"id": "19", "description": "Viaje", "amount": "3850.0", "creditor": "Tarjeta Cívica"},
    ]
    raw = json.dumps(rows, ensure_ascii=False)
    out = read_pool._maybe_wrap_finanz_deudas_read_sql(spec, "SELECT * FROM finance_worker.deudas", raw)
    data = json.loads(out)
    assert "deudas_filas" in data
    meta = data["_totales_resumen_cop"]
    assert meta["suma_todas_las_filas_cop"] == 2360000.0 + 295000.0 * 2 + 215000.0 + 3850.0
    assert meta["total_recomendado_resumen_cop"] == 2360000.0 + 215000.0 + 3850.0
    assert "5" in meta["ids_excluidos_del_total"] and "6" in meta["ids_excluidos_del_total"]


def test_maybe_wrap_finanz_deudas_sin_agregado_no_envuelve() -> None:
    spec = Mock(worker_id="finanz", logical_worker_id=None, schema_name="finance_worker")
    rows = [
        {"id": "5", "description": "Mac Mini - Cuota Abril 2026", "amount": "295000.0", "creditor": "TC Bancolombia"},
        {"id": "6", "description": "Mac Mini - Cuota Mayo 2026", "amount": "295000.0", "creditor": "TC Bancolombia"},
    ]
    raw = json.dumps(rows, ensure_ascii=False)
    out = read_pool._maybe_wrap_finanz_deudas_read_sql(spec, "SELECT * FROM finance_worker.deudas", raw)
    assert out == raw


def test_maybe_wrap_no_finanz_sin_cambio() -> None:
    spec = Mock(worker_id="Job-Hunter", schema_name="finance_worker")
    rows = [{"id": "1", "description": "x", "amount": "1", "creditor": "TC Bancolombia"}]
    raw = json.dumps(rows, ensure_ascii=False)
    out = read_pool._maybe_wrap_finanz_deudas_read_sql(spec, "SELECT * FROM finance_worker.deudas", raw)
    assert out == raw


def test_run_worker_read_sql_applies_wrap() -> None:
    spec = Mock(worker_id="finanz", logical_worker_id=None, schema_name="finance_worker", allowed_tables=[], read_only=True)
    rows = [
        {
            "id": "18",
            "description": "Mac Mini - TC Bancolombia - 8 cuotas mensuales",
            "amount": "2360000.0",
            "creditor": "TC Bancolombia",
        },
        {"id": "5", "description": "Mac Mini - Cuota Abril 2026", "amount": "295000.0", "creditor": "TC Bancolombia"},
        {"id": "6", "description": "Mac Mini - Cuota Mayo 2026", "amount": "295000.0", "creditor": "TC Bancolombia"},
    ]

    def run_query(_q: str) -> str:
        return json.dumps(rows, ensure_ascii=False)

    out = read_pool.run_worker_read_sql(run_query, spec, "SELECT * FROM finance_worker.deudas")
    data = json.loads(out)
    assert "_totales_resumen_cop" in data
    assert data["_totales_resumen_cop"]["total_recomendado_resumen_cop"] == 2360000.0
