"""Loop push: verdict line is the title (watch-friendly); 'sin novedades' sends nothing."""

import importlib.util
import json
from pathlib import Path

_spec = importlib.util.spec_from_file_location("hb_main", Path("services/heartbeat/main.py"))
hb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hb)


def _body(text):
    return json.dumps({"response": text})


def test_verdict_becomes_title():
    title, body = hb._loop_push_parts(_body("worker_a 4\n\nVeredicto: ⚠️ checkout −3% tras el deploy\n\nDetalle **largo** aquí."))
    assert title == "⚠️ checkout −3% tras el deploy"
    assert body == "Detalle largo aquí."


def test_no_news_skips_push():
    assert hb._loop_push_parts(_body("Veredicto: sin novedades\n\nTodo en orden.")) is None
    assert hb._loop_push_parts(_body("**Veredicto:** Sin novedades relevantes")) is None


def test_no_verdict_falls_back():
    title, body = hb._loop_push_parts(_body("Reporte sin línea de veredicto."))
    assert title == "DuckClaw · ciclo /loop" and body == "Reporte sin línea de veredicto."
    # ...unless that report itself says nothing happened.
    assert hb._loop_push_parts(_body("worker_a 10\n\nTick cerrado sin novedades. Estado: TP/SL 6/6.")) is None


def test_truncated_json_body():
    raw = '{"response": "Veredicto: cola supera 2.400 \u2014 revisar workers\n\nmás'
    title, _ = hb._loop_push_parts(raw)
    assert title.startswith("cola supera 2.400")


def test_push_body_skips_a_table_and_uses_the_detail_line() -> None:
    """Seen 18-Oct on the watch: the body was the table header and its '-----' separator."""
    table = (
        "| hora | fuente | hecho con cifra textual | servicio(s) |\n"
        "|---|---|---|---|\n"
        "| 18-oct | status-page | Tráfico al 68% del normal | API |\n"
    )
    _, body = hb._loop_push_parts(_body("Veredicto: Tráfico al 68% del normal → API\n\n" + table))
    assert body == "18-oct · status-page · Tráfico al 68% del normal · API"
    _, body = hb._loop_push_parts(
        _body("Veredicto: Tráfico al 68% → API\nTráfico 68% del normal según la status page (18-oct).\n\n" + table)
    )
    assert body == "Tráfico 68% del normal según la status page (18-oct)."


def test_push_body_drops_a_detail_label() -> None:
    _, body = hb._loop_push_parts(_body("Veredicto: API caída → pagos\nDetalle: status page (18-oct), 40 min."))
    assert body == "status page (18-oct), 40 min."
