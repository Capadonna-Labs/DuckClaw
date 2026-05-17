"""Estética del wizard TUI: bordes y estilos coherentes.

El borde verde en cada paso suele asociarse a «éxito» o a estética retro;
para navegación informativa usamos cian (neutro, habitual en CLIs, poco fatigoso).
El verde se reserva para confirmaciones puntuales (p. ej. borrador guardado, Redis OK).
"""

from __future__ import annotations

from rich.console import Console

# Identidad DuckClaw (TUI Claude-style; no naranja Claude)
DUCK_ACCENT = "#F5C542"
DUCK_ACCENT_ALT = "#2DD4BF"

# Mascota mallard (hex: válidos en Rich y Textual; evitar nombres tipo brown/wheat1)
MASCOT_HEAD = "#2E7D32"
MASCOT_BEAK = "#E65100"
MASCOT_BODY_LIGHT = "#D7CCC8"
MASCOT_BODY_DARK = "#6D4C41"
MASCOT_LEG = "#FF9800"
MASCOT_EYE = "#1a1a1a"
HEADER_BORDER = DUCK_ACCENT
SIDEBAR_STYLE = "dim"
STATUS_DONE = "green"
STATUS_ACTIVE = "bright_white"
STATUS_PENDING = "dim"

# Pasos y guía: información / navegación
PANEL_BORDER = "cyan"

# Aciertos puntuales (Redis OK, túnel activo, etc.)
PANEL_BORDER_SUCCESS = "green"

# Título del panel (Rich): usar markup en ``title=`` porque ``Panel(title_style=…)``
# no existe en todas las versiones de Rich instaladas.
TITLE_STYLE = "bold bright_white"


def panel_title(text: str) -> str:
    """Título de Panel con estilo destacado (compatible con Rich ≥13 sin kwarg title_style)."""
    return f"[bold bright_white]{text}[/]"


# Cabecera de paso «Paso N de M»
STEP_NUMBER_STYLE = "bold bright_white"


def section_label(text: str) -> str:
    """Subtítulo visual dentro de un bloque de texto (panel o guía inicial)."""
    return f"[bold cyan]{text}[/]\n"


def dim_technical(*fragments: str) -> str:
    """Línea técnica opcional (variables, tablas) solo en gris."""
    return "[dim]" + " · ".join(fragments) + "[/]"


def print_dim_rule(console: Console) -> None:
    """Separador horizontal suave entre bloques en consola."""
    from rich.rule import Rule

    console.print(Rule(style="dim"))
