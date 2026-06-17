"""Panel lateral derecho del chat TUI (contexto estilo OpenCode)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rich.panel import Panel
from rich.text import Text

from duckops.sovereign.tui_chat_status import format_usage_tokens


@dataclass
class TuiChatSidebarState:
    worker_id: str
    tenant_id: str
    llm_label: str
    gateway_url: str
    duck_line: str
    policy_summary: str
    policy_ok: bool = True
    policy_degraded: bool = False
    worker_picks: list[Any] = field(default_factory=list)
    last_usage: Any = None
    turn_count: int = 0
    chat_id: str = "sovereign-tui-chat"
    repo_label: str = ""


def _worker_lines(state: TuiChatSidebarState) -> list[str]:
    lines: list[str] = []
    if not state.worker_picks:
        lines.append("[dim]Sin workers en catálogo[/]")
        return lines
    for pick in state.worker_picks[:12]:
        wid = str(getattr(pick, "worker_id", "") or "").strip()
        label = str(getattr(pick, "label", wid) or wid).strip()
        mark = " [cyan]●[/]" if wid == state.worker_id else ""
        lines.append(f"{mark}[bold]{wid}[/] [dim]{label[:28]}[/]")
    if len(state.worker_picks) > 12:
        lines.append(f"[dim]+{len(state.worker_picks) - 12} más[/]")
    return lines


def build_sidebar_text(state: TuiChatSidebarState) -> Text:
    text = Text()
    text.append("Contexto\n", style="bold cyan")
    text.append(f"Modelo  {state.llm_label}\n", style="")
    text.append(f"Worker  {state.worker_id}\n", style="bold")
    text.append(f"Tenant  {state.tenant_id}\n", style="dim")
    text.append(f"Sesión  {state.chat_id}\n", style="dim")
    tok = format_usage_tokens(state.last_usage)
    if tok:
        text.append(f"Tokens  {tok}\n", style="yellow")
    text.append(f"Turnos  {state.turn_count}\n\n", style="dim")

    policy_style = "green" if state.policy_ok and not state.policy_degraded else "yellow"
    if not state.policy_ok:
        policy_style = "red"
    text.append("Policies\n", style="bold cyan")
    text.append(f"{state.policy_summary}\n\n", style=policy_style)

    text.append("DuckDB\n", style="bold cyan")
    text.append_text(Text.from_markup(f"{state.duck_line}\n\n"))

    text.append("Gateway\n", style="bold cyan")
    text.append(f"{state.gateway_url}\n\n", style="cyan")

    text.append("Agentes\n", style="bold cyan")
    for line in _worker_lines(state):
        text.append_text(Text.from_markup(line + "\n"))

    text.append("\nComandos\n", style="bold cyan")
    text.append("/worker <id>  cambiar\n", style="dim")
    text.append("Tab / Shift+Tab  ciclar agente\n", style="dim")
    text.append("/new  nueva sesión\n", style="dim")
    text.append("/retry  repetir\n", style="dim")
    text.append("/status  refrescar\n", style="dim")
    text.append("/web  consola\n", style="dim")
    text.append("/quit  salir\n", style="dim")
    if state.repo_label:
        text.append(f"\n{state.repo_label}\n", style="dim italic")
    return text


def render_sidebar_panel(state: TuiChatSidebarState) -> Panel:
    return Panel(
        build_sidebar_text(state),
        title="[magenta]Context[/]",
        border_style="dim",
        padding=(0, 1),
    )
