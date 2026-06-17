"""Layout estilo Gemini para ``duckops init --chat``."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule
from rich.text import Text

from duckops import __version__ as DUCKOPS_VERSION
from duckops.sovereign.duckdb_health import audit_duckdb, duckdb_chrome_summary
from duckops.sovereign.draft import SovereignDraft
from duckops.sovereign.wizard_theme import DUCK_ACCENT, DUCK_ACCENT_ALT


def _banner_text() -> Text:
    """Título blocky inspirado en Gemini CLI."""
    lines = [
        " ██████╗ ██╗   ██╗ ██████╗██╗  ██╗",
        " ██╔══██╗██║   ██║██╔════╝██║ ██╔╝",
        " ██║  ██║██║   ██║██║     █████╔╝ ",
        " ██║  ██║██║   ██║██║     ██╔═██╗ ",
        " ██████╔╝╚██████╔╝╚██████╗██║  ██╗",
        " ╚═════╝  ╚═════╝  ╚═════╝╚═╝  ╚═╝",
        "        CLAW  ·  Playground",
    ]
    text = Text()
    for i, line in enumerate(lines):
        if i < len(lines) - 1:
            text.append(line + "\n", style=DUCK_ACCENT if i == 0 else DUCK_ACCENT_ALT)
        else:
            text.append(line + "\n", style="dim")
    return text


def render_chat_intro(
    console: Console,
    *,
    base_url: str,
    tenant_id: str,
    repo_root: Path,
    draft: SovereignDraft,
    worker_id: str,
) -> None:
    """Pantalla inicial: banner, tips, contexto y pie (estilo Gemini)."""
    console.print()
    console.print(_banner_text())
    console.print()
    console.print("[bold]Primeros pasos[/]")
    console.print("  1. Escribe un mensaje o usa [cyan]/workers[/] para cambiar agente.")
    console.print("  2. Sé concreto para mejores respuestas del playground.")
    console.print("  3. [cyan]/help[/] · [cyan]/worker <id>[/] · [cyan]/web[/] · [cyan]/quit[/]")
    console.print()
    duck = audit_duckdb(repo_root, draft, quick=True)
    duck_line = duckdb_chrome_summary(duck)
    console.print(
        Panel(
            f"[dim]1[/] DuckDB activa · {duck_line}\n"
            f"[dim]Tenant[/] [bold]{tenant_id}[/] · "
            f"[dim]Worker[/] [bold]{worker_id}[/] · "
            f"[dim]Gateway[/] [cyan]{base_url}[/]",
            border_style="dim",
            padding=(0, 1),
        )
    )
    console.print()
    console.print(
        Panel(
            Text(" Escribe tu mensaje ", style="dim"),
            title="[magenta]*[/]",
            title_align="left",
            border_style="magenta",
            padding=(0, 1),
        )
    )
    console.print(Rule(style="dim"))
    console.print(
        f"  [cyan]{repo_root}[/]  "
        f"[dim]·[/]  [magenta]playground local[/]  "
        f"[dim]·[/]  DuckClaw v{DUCKOPS_VERSION}",
        style="dim",
    )
    console.print()


