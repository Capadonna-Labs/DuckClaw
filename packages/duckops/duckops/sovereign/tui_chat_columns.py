"""Layout dos columnas estilo OpenCode (chat ancho + sidebar fijo)."""

from __future__ import annotations

from rich.console import Console, Group, RenderableType
from rich.layout import Layout
from rich.panel import Panel
from rich.rule import Rule

from duckops.sovereign.tui_chat_sidebar import TuiChatSidebarState, render_sidebar_panel

_MAIN_RATIO = 7
_SIDEBAR_RATIO = 3


def _split_layout(main: RenderableType, sidebar_state: TuiChatSidebarState) -> Layout:
    layout = Layout()
    layout.split_row(
        Layout(main, name="main", ratio=_MAIN_RATIO),
        Layout(render_sidebar_panel(sidebar_state), name="sidebar", ratio=_SIDEBAR_RATIO),
    )
    return layout


def render_intro_columns(
    console: Console,
    *,
    left: RenderableType,
    sidebar_state: TuiChatSidebarState,
) -> None:
    console.print(_split_layout(left, sidebar_state))


def render_chat_turn(
    console: Console,
    *,
    user_line: str,
    reply: str,
    agent_title: str,
    sidebar_state: TuiChatSidebarState,
) -> None:
    main = Group(
        Panel(user_line, title="Tú", border_style="dim", padding=(0, 1)),
        Panel(
            reply or "[dim](sin respuesta)[/]",
            title=agent_title,
            border_style="yellow",
            padding=(0, 1),
        ),
    )
    console.print(_split_layout(main, sidebar_state))


def render_input_chrome(
    console: Console,
    *,
    llm_label: str,
    worker_id: str,
    tenant_id: str,
) -> None:
    """Barra inferior tipo OpenCode antes del prompt interactivo."""

    console.print(Rule(style="dim"))
    console.print(
        f"[cyan]{llm_label}[/] · worker [bold]{worker_id}[/] · "
        f"tenant [dim]{tenant_id}[/] · [dim]Tab[/] agente · [dim]/help[/]"
    )
