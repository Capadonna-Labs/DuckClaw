"""unescape_telegram_markdown_v2_layers evita acumulación de barras al re-escapar."""

from __future__ import annotations

import time

import pytest

from duckclaw.graphs.on_the_fly_commands import (
    _telegram_safe,
    execute_tasks,
    unescape_telegram_markdown_v2_layers,
)


def test_unescape_one_layer_exclamation() -> None:
    assert unescape_telegram_markdown_v2_layers(r"hola\!") == "hola!"


def test_unescape_triple_before_exclamation_matches_double_escape_noise() -> None:
    # Simula salida ya escapada dos veces (modelo + gateway o historial + gateway).
    assert unescape_telegram_markdown_v2_layers(r"hola\\\!") == "hola!"


def test_telegram_safe_after_unescape_is_stable() -> None:
    raw = "¡Hola Valentina! Soy Leila."
    once = _telegram_safe(raw)
    twice = _telegram_safe(once)
    assert "\\" in twice
    healed = unescape_telegram_markdown_v2_layers(twice)
    assert healed == raw
    assert _telegram_safe(healed) == once


def test_roundtrip_plain() -> None:
    s = "Sin especiales raros"
    assert unescape_telegram_markdown_v2_layers(s) == s
    assert unescape_telegram_markdown_v2_layers(_telegram_safe(s)) == s


def test_execute_tasks_shows_worker_without_backslash_before_hyphen(monkeypatch: pytest.MonkeyPatch) -> None:
    """Nombre SIATA-Analyst en /tasks: espacio en lugar de guion para no exigir \\- en MarkdownV2."""

    def _fake_get_activity(_chat_id: object) -> dict:
        return {
            "status": "BUSY",
            "task": "Scrapeo radar",
            "worker_id": "SIATA-Analyst",
            "started_at": int(time.time()) - 3,
        }

    monkeypatch.setattr("duckclaw.graphs.activity.get_activity", _fake_get_activity)
    out = execute_tasks(None, "1726618406")
    assert "SIATA\\-Analyst" not in out
    assert "SIATA Analyst" in out or "SIATA" in unescape_telegram_markdown_v2_layers(out)
