"""Atajos globales (spec §4)."""

from __future__ import annotations

from typing import Any, Callable

from prompt_toolkit.key_binding import KeyBindings

NAV_BACK = "__sovereign_back__"
NAV_QUICK_SAVE = "__sovereign_quick_save__"
NAV_SERVICE_TEST = "__sovereign_service_test__"
NAV_AUTOFILL = "__sovereign_autofill__"


def build_key_bindings(
    *,
    on_service_test: Callable[[], None] | None = None,
) -> KeyBindings:
    """
    Ctrl+Z / Esc → NAV_BACK.
    Ctrl+S → NAV_QUICK_SAVE.
    Ctrl+R → prueba de servicio (callback).
    Tab → NAV_AUTOFILL (el bucle usa el default mostrado).
    """
    kb = KeyBindings()

    @kb.add("c-z")
    @kb.add("escape")
    def _back(event: Any) -> None:
        event.app.exit(result=NAV_BACK)

    @kb.add("c-s")
    def _save(event: Any) -> None:
        event.app.exit(result=NAV_QUICK_SAVE)

    @kb.add("c-r")
    def _test(event: Any) -> None:
        if on_service_test:
            on_service_test()
        event.app.exit(result=NAV_SERVICE_TEST)

    @kb.add("tab")
    def _autofill(event: Any) -> None:
        event.app.exit(result=NAV_AUTOFILL)

    return kb
