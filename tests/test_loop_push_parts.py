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


def test_no_news_with_approval_question_still_pushes():
    raw = _body("Veredicto: sin novedades\n\nPlan de 7 órdenes.\n\n¿Apruebas el plan para que cree las señales?")
    assert hb._loop_push_parts(raw) == ("Decisión pendiente", "¿Apruebas el plan para que cree las señales?")


def test_no_verdict_falls_back():
    title, body = hb._loop_push_parts(_body("Reporte sin línea de veredicto."))
    assert title == "DuckClaw · ciclo /aware" and body == "Reporte sin línea de veredicto."
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


def test_broken_verdict_title_is_replaced():
    """A response that lost a chunk upstream ('WTI cie) pese a…') never becomes the watch title."""
    title, body = hb._loop_push_parts(_body("Veredicto: WTI cie) pese a Brent plano → XLE\n\nWTI noviembre +2,22% a 103,66 $."))
    assert title == "DuckClaw · aviso" and body.startswith("WTI noviembre")


def test_broken_detail_line_falls_back_to_the_table_row_then_to_the_title():
    """22-Oct: the agent's detail line lost a chunk ('...comprometidos con el de) (La Jornada, 21-oct).')."""
    broken = 'Netanyahu dice que él y Trump están "comprometidos con el de) (La Jornada, 21-oct).'
    table = "| hora | fuente | hecho |\n|---|---|---|\n| 21-oct | La Jornada | Netanyahu: completar el derrocamiento del régimen iraní |"
    title, body = hb._loop_push_parts(_body(f'Veredicto: Netanyahu: "derrocar el régimen iraní" → XLE\n\n{broken}\n\n{table}'))
    assert title.startswith("Netanyahu") and body == "21-oct · La Jornada · Netanyahu: completar el derrocamiento del régimen iraní"
    title, body = hb._loop_push_parts(_body(f'Veredicto: Netanyahu: "derrocar el régimen iraní" → XLE\n\n{broken}'))
    assert body == title or body == 'Netanyahu: "derrocar el régimen iraní" → XLE'  # nothing intact: the (good) title is the body
    assert hb._loop_push_parts(_body("Veredicto: Brent +2%\n\nBrent sube 2% (Reuters, 22-oct)."))[1] == "Brent sube 2% (Reuters, 22-oct)."  # intact lines untouched


def test_a_moved_figure_on_the_same_story_is_not_pushed_again() -> None:
    import calendar, time
    now = calendar.timegm((2026, 11, 6, 16, 40, 0, 0, 0, 0))
    recent = ["06-Nov 15:40 UTC · Checkout: tasa de error sube a 3% en la región → api/web"]
    assert hb._repeats("Checkout error sube a 3,5% (panel) tras el deploy → api/web", recent, now)
    assert not hb._repeats("Checkout error sube a 3,5% tras el deploy → api", recent, now)        # other target
    assert not hb._repeats("Proveedor de pagos anuncia mantenimiento → api/web", recent, now)       # other story
    assert not hb._repeats("Checkout error sube a 3,5% (panel) → api/web", recent, now + 7 * 3600)  # older than 6 h
    # A forced fact has no target: it repeats any recent verdict on the same story (27-nov, Jazan forced 1 h after its alert).
    fact = "Checkout: error 3% en la región tras el deploy"
    assert not hb._repeats(fact, recent, now)
    assert hb._repeats(fact, recent, now, any_target=True)


def test_forced_line_the_model_marks_as_already_sent_is_dropped(monkeypatch):
    monkeypatch.setenv("DUCKCLAW_PUSH_FORCE_PATTERN", r"tanker.*mine")
    row = "| 26-nov 21:10 | CNA (https://www.channelnewsasia.com/business/brent-settles-higher-mine-strikes-tanker-attack-6012345) | Tanker hit a mine, Brent settles up | XLE |"
    assert hb._loop_push_parts(_body("Veredicto: sin novedades\n\n" + row))[1] == "Tanker hit a mine, Brent settles up"
    assert hb._loop_push_parts(_body("Veredicto: sin novedades\n- Tanker hit a mine off Khasab. Ya avisado.\n")) is None
    # 27-nov: the model said so in its closing note, not on the row.
    note = "\n\nMotivo: el ataque a Ras Tanura y la parada de Jazan ya se avisaron el 26-nov; sin dato nuevo."
    row = "| 27-nov 07:49 | ET | Crude −0,25%; ataque a refinería de Jazan (parada parcial) | XLE |"
    monkeypatch.setenv("DUCKCLAW_PUSH_FORCE_PATTERN", r"ataque.*refiner")
    assert hb._loop_push_parts(_body("Veredicto: sin novedades\n\n" + row + note)) is None
    assert hb._loop_push_parts(_body("Veredicto: sin novedades\n\n" + row))[0].startswith("Alerta forzada")


def test_quiet_hours_hold_interval_pushes_but_not_decisions(monkeypatch):
    monkeypatch.setenv("DUCKCLAW_PUSH_QUIET_HOURS", "22-6")
    assert [h for h in range(24) if hb._push_quiet_now(h)] == [0, 1, 2, 3, 4, 5, 22, 23]
    monkeypatch.setattr(hb, "_push_quiet_now", lambda hour=None: True)
    assert hb._held_by_quiet_hours(("Brent cierra $92", "detalle"), "t") is True
    assert hb._held_by_quiet_hours(("Decisión pendiente", "¿Apruebas?"), "t") is False


def test_quiet_hours_off_when_unset_or_malformed(monkeypatch):
    monkeypatch.delenv("DUCKCLAW_PUSH_QUIET_HOURS", raising=False)
    assert not any(hb._push_quiet_now(h) for h in range(24))
    monkeypatch.setenv("DUCKCLAW_PUSH_QUIET_HOURS", "noche")
    assert not hb._push_quiet_now(3)
    monkeypatch.setenv("DUCKCLAW_PUSH_QUIET_HOURS", "1-5")
    assert [h for h in range(24) if hb._push_quiet_now(h)] == [1, 2, 3, 4]


def test_force_pattern_overrides_no_news(monkeypatch):
    text = "Veredicto: sin novedades\n\n| 24-nov 07:10 | Reuters | 2 tankers hit mines near the strait, fire on board | XLE |\n"
    assert hb._loop_push_parts(_body(text)) is None
    monkeypatch.setenv("DUCKCLAW_PUSH_FORCE_PATTERN", r"tanker.*mine")
    title, body = hb._loop_push_parts(_body(text))
    assert title.startswith("Alerta forzada")
    assert body == "2 tankers hit mines near the strait, fire on board"
    title, body = hb._loop_push_parts(_body("Veredicto: sin novedades\n- Tanker hit a mine off Fujairah\n"))
    assert body == "Tanker hit a mine off Fujairah"
    # A row without a time of day is an undated (often stale) headline: not forced.
    assert hb._loop_push_parts(_body(text.replace("24-nov 07:10", "24-nov"))) is None
    monkeypatch.setenv("DUCKCLAW_PUSH_FORCE_PATTERN", "(")
    assert hb._loop_push_parts(_body(text)) is None


def test_force_pattern_bypasses_quiet_hours(monkeypatch):
    monkeypatch.setenv("DUCKCLAW_PUSH_QUIET_HOURS", "0-24")
    monkeypatch.setattr(hb, "_push_quiet_now", lambda hour=None: True)
    assert hb._held_by_quiet_hours(("Rally en bonos", "nada"), "t")
    monkeypatch.setenv("DUCKCLAW_PUSH_FORCE_PATTERN", r"drones?.*refiner")
    assert not hb._held_by_quiet_hours(("4 drones sobre la refinería", "x"), "t")
