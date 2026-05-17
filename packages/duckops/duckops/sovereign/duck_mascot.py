"""Mascota mallard pixel art: frames, estados, inercia y widget Textual."""

from __future__ import annotations

import itertools
import random
import re
from enum import Enum
from typing import Iterator

from rich.text import Text

from duckops.sovereign.wizard_theme import (
    DUCK_ACCENT,
    DUCK_ACCENT_ALT,
    MASCOT_BEAK,
    MASCOT_BODY_DARK,
    MASCOT_BODY_LIGHT,
    MASCOT_EYE,
    MASCOT_HEAD,
    MASCOT_LEG,
)

_H, _B, _L, _D, _G, _E = (
    MASCOT_HEAD,
    MASCOT_BEAK,
    MASCOT_BODY_LIGHT,
    MASCOT_BODY_DARK,
    MASCOT_LEG,
    MASCOT_EYE,
)


class MascotState(str, Enum):
    IDLE = "idle"
    WALKING = "walking"
    WORKING = "working"


_FRAME_IDLE: tuple[list[str], ...] = (
    [
        f"    [{_H}]▄███▄[/]",
        f"   [{_H}]█[/][{_E}]●[/][{_H}]████▌[/]",
        f"    [{_B}]▐█▌[/]",
        f"  [{_L}]████[/][{_D}]▓▓░[/]",
        f"   [{_L}]███[/][{_D}]▓░░[/]",
        f"    [{_G}]▌[/] [{_G}]█[/]",
    ],
    [
        f"    [{_H}]▄███▄[/]",
        f"   [{_H}]█[/][{_E}]●[/][{_H}]████▌[/]",
        f"    [{_B}]▐█▌[/]",
        f"   [{_L}]████[/][{_D}]▓▓░[/]",
        f"    [{_L}]███[/][{_D}]▓░░[/]",
        f"     [{_G}]▌[/][{_G}]█[/]",
    ],
)

_FRAME_WALKING: tuple[list[str], ...] = (
    [
        f"    [{_H}]▄███▄[/]",
        f"   [{_H}]█[/][{_E}]●[/][{_H}]████▌[/]",
        f"    [{_B}]▐█▌[/]",
        f"  [{_L}]████[/][{_D}]▓▓░[/]",
        f"   [{_L}]███[/][{_D}]▓░░[/]",
        f"   [{_G}]█[/]  [{_G}]▌[/]",
    ],
    [
        f"    [{_H}]▄███▄[/]",
        f"   [{_H}]█[/][{_E}]●[/][{_H}]████▌[/]",
        f"    [{_B}]▐█▌[/]",
        f"  [{_L}]████[/][{_D}]▓▓░[/]",
        f"   [{_L}]███[/][{_D}]▓░░[/]",
        f"    [{_G}]▌[/] [{_G}]█[/]",
    ],
)

# Plantilla WORKING: {{spinner}} escapa llaves Rich; solo {spinner} se sustituye.
_FRAME_WORKING_TEMPLATE: tuple[str, ...] = (
    f"    [{_H}]▄███▄[/]",
    f"   [{_H}]█[/][{_E}]●[/][{_H}]████▌[/]",
    f"    [{_B}]▐▌[/][{_G}]█[/]",
    f"  [{_L}]████[/][{_D}]▓▓░[/]",
    f"   [{_L}]███[/][{_D}]▓░░[/]",
    f"    [{DUCK_ACCENT}]╭[/][{DUCK_ACCENT_ALT}]{{spinner}}[/][{DUCK_ACCENT}]╯[/] claw",
)

FRAMES_BY_STATE: dict[MascotState, tuple[list[str], ...]] = {
    MascotState.IDLE: _FRAME_IDLE,
    MascotState.WALKING: _FRAME_WALKING,
}

_SPINNERS: tuple[str, ...] = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")


def _strip_markup(line: str) -> str:
    return re.sub(r"\[[^\]]*\]", "", line)


class DuckMascot:
    """Motor de frames con inercia, pathfinding básico y spinner en WORKING."""

    def __init__(
        self,
        *,
        state: MascotState = MascotState.IDLE,
        x: int = 0,
        y: int = 0,
    ) -> None:
        self.state = state
        self.x = x
        self.y = y
        self.target_x = x
        self.target_y = y
        self._cycles: dict[MascotState, Iterator[int]] = {
            s: itertools.cycle(range(len(FRAMES_BY_STATE[s])))
            for s in (MascotState.IDLE, MascotState.WALKING)
        }
        self._spinner_cycle = itertools.cycle(_SPINNERS)
        self._current_spinner = next(self._spinner_cycle)
        self._frame_index = 0

    @property
    def width(self) -> int:
        lines = self.current_lines()
        if not lines:
            return 8
        return max(len(_strip_markup(l)) for l in lines)

    @property
    def height(self) -> int:
        return len(self.current_lines())

    def set_state(self, state: MascotState) -> None:
        if state != self.state:
            self.state = state
            self._frame_index = 0
            if state == MascotState.WORKING:
                self._current_spinner = next(self._spinner_cycle)

    def tick(self) -> None:
        """Avanza un frame (idle/walk) o el spinner (working)."""
        if self.state == MascotState.WORKING:
            self._current_spinner = next(self._spinner_cycle)
            return
        self._frame_index = next(self._cycles[self.state])

    def current_lines(self) -> list[str]:
        if self.state == MascotState.WORKING:
            return [
                line.format(spinner=self._current_spinner)
                for line in _FRAME_WORKING_TEMPLATE
            ]
        frames = FRAMES_BY_STATE[self.state]
        return list(frames[self._frame_index % len(frames)])

    def render_rich(self, *, pad_x: int = 0, pad_y: int = 0) -> Text:
        out = Text()
        for _ in range(pad_y):
            out.append("\n")
        indent = " " * pad_x
        for line in self.current_lines():
            out.append(indent)
            out.append_text(Text.from_markup(line))
            out.append("\n")
        return out

    def update_logic(self, max_x: int, max_y: int) -> None:
        """Movimiento hacia objetivo; en WORKING solo anima el spinner."""
        if self.state == MascotState.WORKING:
            self.tick()
            return

        if self.x == self.target_x and self.y == self.target_y:
            if random.random() < 0.15:
                self.target_x = random.randint(0, max(0, max_x))
                self.target_y = random.randint(0, max(0, max_y))
                self.state = MascotState.WALKING
            else:
                self.state = MascotState.IDLE
        else:
            if self.x < self.target_x:
                self.x += 1
            elif self.x > self.target_x:
                self.x -= 1
            if self.y < self.target_y:
                self.y += 1
            elif self.y > self.target_y:
                self.y -= 1
            self.state = MascotState.WALKING

        self.tick()

    def random_step(self, max_x: int, max_y: int) -> None:
        """Compat demo: elige destino y avanza un paso."""
        self.target_x = random.randint(0, max(0, max_x))
        self.target_y = random.randint(0, max(0, max_y))
        self.update_logic(max_x, max_y)


def _textual_available() -> bool:
    try:
        import textual  # noqa: F401

        return True
    except ImportError:
        return False


if _textual_available():
    from textual.app import App, ComposeResult
    from textual.reactive import reactive
    from textual.widget import Widget

    class DuckMascotWidget(Widget):
        """Widget Textual: refresca solo su región (~10 fps)."""

        DEFAULT_CSS = """
        DuckMascotWidget {
            width: 1fr;
            height: 10;
            background: #0d0d0d;
            overflow: hidden;
        }
        """

        state: reactive[MascotState] = reactive(MascotState.IDLE)

        def __init__(self, **kwargs: object) -> None:
            super().__init__(**kwargs)
            self._mascot = DuckMascot()
            self._bounds_x = 16
            self._bounds_y = 3

        def on_mount(self) -> None:
            self.set_interval(0.1, self._animate)

        def _animate(self) -> None:
            self._mascot.update_logic(self._bounds_x, self._bounds_y)
            self.state = self._mascot.state
            self.refresh()

        def set_mascot_state(self, state: MascotState) -> None:
            self._mascot.set_state(state)
            self.state = state
            self.refresh()

        def render(self) -> Text:
            return self._mascot.render_rich(
                pad_x=self._mascot.x,
                pad_y=self._mascot.y,
            )

    class DuckMascotApp(App[None]):
        TITLE = "DuckClaw mascota"
        CSS = """
        Screen { background: #0d0d0d; }
        #hint { padding: 1 2; color: #2dd4bf; }
        """

        def compose(self) -> ComposeResult:
            from textual.widgets import Footer, Header, Static

            yield Header()
            yield Static(
                "DuckClaw · IDLE / WALKING / WORKING",
                id="hint",
            )
            yield DuckMascotWidget(id="duck")
            yield Footer()

else:

    class DuckMascotWidget:  # type: ignore[no-redef]
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise RuntimeError("Instala textual (uv sync en packages/duckops)")

    class DuckMascotApp:  # type: ignore[no-redef]
        def run(self) -> None:
            raise RuntimeError("Instala textual (uv sync en packages/duckops)")


def run_mascot_demo() -> int:
    if not _textual_available():
        raise SystemExit("Falta 'textual'. Ejecuta: uv sync")
    DuckMascotApp().run()
    return 0
