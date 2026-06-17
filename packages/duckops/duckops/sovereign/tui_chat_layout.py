"""Layout estilo OpenCode para ``duckops init --chat``."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console, Group
from rich.text import Text

from duckops.sovereign.duckdb_health import audit_duckdb, duckdb_chrome_summary
from duckops.sovereign.draft import SovereignDraft
from duckops.sovereign.wizard_theme import DUCK_ACCENT, DUCK_ACCENT_ALT
from duckops.sovereign.tui_chat_columns import render_intro_columns
from duckops.sovereign.tui_chat_sidebar import TuiChatSidebarState


def duckclaw_banner_text() -> Text:
    """Título blocky DUCK + subtítulo CLAW · Playground."""

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
    sidebar_state: TuiChatSidebarState,
) -> None:
    """Intro compacta: tips a la izquierda, contexto persistente a la derecha."""

    console.print()
    left = Group(
        duckclaw_banner_text(),
        Text(""),
        Text.from_markup(
            "[bold]Atajos[/]\n"
            "  [cyan]Tab[/] — siguiente agente del catálogo DB\n"
            "  [cyan]/new[/] · [cyan]/retry[/] · [cyan]/workers[/] · [cyan]/web[/] · [cyan]/quit[/]"
        ),
        Text(""),
        Text.from_markup(
            "[dim]Al enviar el primer mensaje el banner desaparece. "
            "El panel [magenta]Context[/] sigue a la derecha en cada turno.[/]"
        ),
    )
    duck = audit_duckdb(repo_root, draft, quick=True)
    sidebar_state.duck_line = duckdb_chrome_summary(duck)
    sidebar_state.gateway_url = base_url
    sidebar_state.worker_id = worker_id
    sidebar_state.tenant_id = tenant_id
    sidebar_state.repo_label = str(repo_root)
    render_intro_columns(console, left=left, sidebar_state=sidebar_state)
