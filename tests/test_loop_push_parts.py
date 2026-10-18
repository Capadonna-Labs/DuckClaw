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
    title, body = hb._loop_push_parts(_body("quant_analyst 4\n\nVeredicto: ⚠️ XLE −3% tras post de Trump\n\nDetalle **largo** aquí."))
    assert title == "⚠️ XLE −3% tras post de Trump"
    assert body == "Detalle largo aquí."


def test_no_news_skips_push():
    assert hb._loop_push_parts(_body("Veredicto: sin novedades\n\nTodo en orden.")) is None
    assert hb._loop_push_parts(_body("**Veredicto:** Sin novedades relevantes")) is None


def test_no_verdict_falls_back():
    title, body = hb._loop_push_parts(_body("Reporte sin línea de veredicto."))
    assert title == "DuckClaw · ciclo /loop" and body == "Reporte sin línea de veredicto."


def test_truncated_json_body():
    raw = '{"response": "Veredicto: GLD rompe 2.400 \u2014 revisar stop\n\nmás'
    title, _ = hb._loop_push_parts(raw)
    assert title.startswith("GLD rompe 2.400")
