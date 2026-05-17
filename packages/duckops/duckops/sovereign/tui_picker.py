"""Listas interactivas: Espacio marca · Enter confirma · Esc atrás."""

from __future__ import annotations

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import Window
from prompt_toolkit.layout.controls import FormattedTextControl

from duckops.sovereign.keys import NAV_BACK, NAV_RESET


class PickerCancelled(Exception):
    """Usuario pulsó Esc / Ctrl+Z."""


class WizardResetRequested(Exception):
    """Usuario pulsó Ctrl+Shift+R en un picker."""


def run_list_picker(
    title: str,
    labels: list[str],
    *,
    values: list[str] | None = None,
    initial_index: int = 0,
    hint: str = "↑↓ mover · Espacio marcar · Enter confirmar · Esc atrás",
) -> str:
    """
    Devuelve el ``value`` elegido (o el label si ``values`` es None).
    Lanza ``PickerCancelled`` si cancela.
    """
    if not labels:
        raise ValueError("lista vacía")
    vals = values if values is not None else labels
    if len(vals) != len(labels):
        raise ValueError("labels y values deben tener la misma longitud")

    cursor = max(0, min(initial_index, len(labels) - 1))
    selected = cursor

    def _render() -> FormattedText:
        lines: list[tuple[str, str]] = [("class:title", title), ("", "\n")]
        for i, lab in enumerate(labels):
            pointer = "› " if i == cursor else "  "
            bullet = "● " if i == selected else "○ "
            style = "class:selected" if i == selected else ""
            lines.append((style, f"{pointer}{bullet}{lab}\n"))
        lines.append(("", f"\n{hint}\n"))
        return FormattedText(lines)

    control = FormattedTextControl(lambda: _render())
    kb = KeyBindings()

    @kb.add("up")
    def _up(event) -> None:
        nonlocal cursor
        cursor = max(0, cursor - 1)
        event.app.invalidate()

    @kb.add("down")
    def _down(event) -> None:
        nonlocal cursor
        cursor = min(len(labels) - 1, cursor + 1)
        event.app.invalidate()

    @kb.add("home")
    def _home(event) -> None:
        nonlocal cursor
        cursor = 0
        event.app.invalidate()

    @kb.add("end")
    def _end(event) -> None:
        nonlocal cursor
        cursor = len(labels) - 1
        event.app.invalidate()

    @kb.add(" ")
    def _space(event) -> None:
        nonlocal selected
        selected = cursor
        event.app.invalidate()

    @kb.add("enter")
    def _enter(event) -> None:
        event.app.exit(result=vals[selected])

    @kb.add("escape")
    @kb.add("c-z")
    def _back(event) -> None:
        event.app.exit(result=NAV_BACK)

    @kb.add("f10")
    def _reset(event) -> None:
        event.app.exit(result=NAV_RESET)

    pt_style = Style.from_dict(
        {
            "title": "bold",
            "selected": "bold ansicyan",
        }
    )
    app = Application(
        layout=Layout(Window(control)),
        key_bindings=kb,
        style=pt_style,
        full_screen=False,
    )
    result = app.run()
    if result == NAV_BACK:
        raise PickerCancelled()
    if result == NAV_RESET:
        raise WizardResetRequested()
    return str(result)


def pick_one_index(
    title: str,
    labels: list[str],
    *,
    initial_index: int = 0,
    hint: str | None = None,
) -> int:
    """Devuelve índice en ``labels``."""
    if not labels:
        raise ValueError("lista vacía")
    values = [str(i) for i in range(len(labels))]
    raw = run_list_picker(
        title,
        labels,
        values=values,
        initial_index=initial_index,
        hint=hint or "↑↓ mover · Espacio marcar · Enter confirmar · Esc atrás",
    )
    return int(raw)
